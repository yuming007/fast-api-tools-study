from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query

from app.common.bootstrap import bootstrap_dependencies
from app.common.clickhouse_client import get_clickhouse_client
from app.common.config import get_settings
from app.common.elasticsearch_client import get_elasticsearch_client
from app.common.logging import configure_logging
from app.common.redis_client import close_redis_client, get_redis_client
from app.common.redis_state import (
    acquire_lock,
    build_search_cache_key,
    release_lock,
    search_cache_lock_key,
    set_cache_value,
    wait_for_cached_value,
)
from app.common.schemas import AnalyticsSummary, HealthResponse, SearchHit, SearchResponse, TrendPoint

settings = get_settings()
logger = configure_logging("search-service")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 搜索服务需要依赖 Redis、ClickHouse 和 Elasticsearch。
    await bootstrap_dependencies(
        "search-service",
        needs_redis=True,
        needs_clickhouse=True,
        needs_elasticsearch=True,
    )
    try:
        yield
    finally:
        await close_redis_client()


app = FastAPI(
    title="search-service",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def healthcheck() -> HealthResponse:
    """搜索服务健康检查。"""

    return HealthResponse(service="search-service")


@app.get("/search", response_model=SearchResponse)
async def search_articles(
    q: str | None = None,
    topic: str | None = None,
    source: str | None = None,
    size: int = Query(default=10, ge=1, le=20),
) -> SearchResponse:
    """先查 Redis 缓存，未命中时再走 Elasticsearch。"""

    redis_client = get_redis_client()
    cache_key = await build_search_cache_key(q, topic, source, size)
    cached = await redis_client.get(cache_key)
    if cached:
        payload = json.loads(cached)
        payload["cached"] = True
        return SearchResponse.model_validate(payload)

    lock_key = search_cache_lock_key(cache_key)
    lock_token = await acquire_lock(
        lock_key,
        ttl_seconds=settings.search_cache_rebuild_lock_seconds,
    )
    if lock_token is None:
        cached = await wait_for_cached_value(
            cache_key,
            timeout_ms=settings.search_cache_wait_timeout_ms,
        )
        if cached:
            payload = json.loads(cached)
            payload["cached"] = True
            return SearchResponse.model_validate(payload)

    filters = []
    if topic:
        filters.append({"term": {"topic": topic}})
    if source:
        filters.append({"term": {"source": source}})

    if q:
        must = [
            {
                "multi_match": {
                    "query": q,
                    "fields": ["title^3", "summary^2", "content"],
                }
            }
        ]
    else:
        must = [{"match_all": {}}]

    try:
        response = await asyncio.to_thread(
            get_elasticsearch_client().search,
            index=settings.elasticsearch_index,
            body={
                "size": size,
                "query": {"bool": {"must": must, "filter": filters}},
                "sort": [{"published_at": {"order": "desc", "unmapped_type": "date"}}],
                "highlight": {"fields": {"content": {}, "summary": {}}},
            },
        )

        hits = []
        for hit in response["hits"]["hits"]:
            source_payload = hit["_source"]
            highlight_parts = []
            if "highlight" in hit:
                for values in hit["highlight"].values():
                    highlight_parts.extend(values[:1])
            hits.append(
                SearchHit(
                    external_id=source_payload["external_id"],
                    task_id=source_payload["task_id"],
                    run_id=source_payload["run_id"],
                    topic=source_payload["topic"],
                    source=source_payload["source"],
                    author=source_payload["author"],
                    title=source_payload["title"],
                    summary=source_payload["summary"],
                    published_at=source_payload.get("published_at"),
                    highlight=highlight_parts[:2],
                )
            )

        result = SearchResponse(
            cached=False,
            total=response["hits"]["total"]["value"],
            hits=hits,
        )
        await set_cache_value(cache_key, result.model_dump_json(), settings.search_cache_ttl_seconds)
        return result
    finally:
        if lock_token is not None:
            await release_lock(lock_key, lock_token)


def load_analytics_summary_data(hours: int) -> tuple[tuple, list[tuple], list[tuple]]:
    """在线程里执行 ClickHouse 汇总查询，避免阻塞 FastAPI 事件循环。"""

    client = get_clickhouse_client()
    summary_row = client.query(
        f"""
        SELECT
            count() AS total_documents,
            uniq(run_id) AS unique_runs,
            round(avg(fetch_latency_ms), 2) AS avg_fetch_latency_ms,
            sum(body_length) AS total_body_length
        FROM crawl_metrics
        WHERE event_time >= now() - INTERVAL {hours} HOUR
        """
    ).result_rows[0]
    source_rows = client.query(
        f"""
        SELECT source, count() AS documents
        FROM crawl_metrics
        WHERE event_time >= now() - INTERVAL {hours} HOUR
        GROUP BY source
        ORDER BY documents DESC
        """
    ).result_rows
    top_task_rows = client.query(
        f"""
        SELECT task_id, count() AS documents
        FROM crawl_metrics
        WHERE event_time >= now() - INTERVAL {hours} HOUR
        GROUP BY task_id
        ORDER BY documents DESC
        LIMIT 5
        """
    ).result_rows
    return summary_row, source_rows, top_task_rows


@app.get("/analytics/summary", response_model=AnalyticsSummary)
async def analytics_summary(hours: int = Query(default=24, ge=1, le=168)) -> AnalyticsSummary:
    """返回指定时间窗口内的汇总分析数据。"""

    summary_row, source_rows, top_task_rows = await asyncio.to_thread(load_analytics_summary_data, hours)
    total_documents, unique_runs, avg_latency, total_body_length = summary_row

    return AnalyticsSummary(
        hours=hours,
        total_documents=int(total_documents or 0),
        unique_runs=int(unique_runs or 0),
        avg_fetch_latency_ms=float(avg_latency or 0),
        total_body_length=int(total_body_length or 0),
        source_breakdown=[
            {"source": source_name, "documents": int(documents)}
            for source_name, documents in source_rows
        ],
        top_tasks=[
            {"task_id": int(task_id), "documents": int(documents)}
            for task_id, documents in top_task_rows
        ],
    )


def load_analytics_trend_data(hours: int) -> list[tuple]:
    """在线程里执行 ClickHouse 趋势查询。"""

    client = get_clickhouse_client()
    return client.query(
        f"""
        SELECT
            formatDateTime(toStartOfHour(event_time), '%Y-%m-%d %H:00:00') AS bucket,
            count() AS documents
        FROM crawl_metrics
        WHERE event_time >= now() - INTERVAL {hours} HOUR
        GROUP BY bucket
        ORDER BY bucket
        """
    ).result_rows


@app.get("/analytics/trend", response_model=list[TrendPoint])
async def analytics_trend(hours: int = Query(default=24, ge=1, le=168)) -> list[TrendPoint]:
    """返回按小时聚合的趋势数据。"""

    rows = await asyncio.to_thread(load_analytics_trend_data, hours)
    return [TrendPoint(bucket=bucket, documents=int(documents)) for bucket, documents in rows]
