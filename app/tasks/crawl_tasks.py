from __future__ import annotations

import asyncio
import hashlib

import requests

from app.common.celery_app import celery_app
from app.common.clickhouse_client import insert_crawl_metrics
from app.common.config import get_settings
from app.common.elasticsearch_client import bulk_index_articles
from app.common.logging import configure_logging
from app.common.mysql import get_session_factory
from app.common.redis_state import invalidate_search_cache, mark_article_deduplicated, record_worker_failure, record_worker_success
from app.common.repositories import fail_run, finish_run, get_task, mark_run_running, upsert_article_metadata
from app.common.schemas import CrawlMessage, SourceBatchResponse
from app.common.time_utils import parse_iso_datetime, utcnow

settings = get_settings()
logger = configure_logging("celery-crawl-worker")


def fetch_source_payload(message: CrawlMessage) -> SourceBatchResponse:
    """向模拟源服务请求一批文章数据。"""

    response = requests.get(
        f"{settings.mock_source_base_url.rstrip('/')}{message.source_path}",
        params={
            "topic": message.topic,
            "batch": message.batch_size,
            "task_id": message.task_id,
            "run_id": message.run_id,
        },
        timeout=settings.request_timeout_seconds,
    )
    response.raise_for_status()
    return SourceBatchResponse.model_validate(response.json())


async def _execute_crawl_run_async(message_payload: dict) -> dict:
    """真正的异步执行逻辑，由 Celery 任务同步包装调用。"""

    message = CrawlMessage.model_validate(message_payload)
    session_factory = get_session_factory()

    async with session_factory() as session:
        task = await get_task(session, message.task_id)
        if task is None:
            raise RuntimeError(f"Task {message.task_id} no longer exists")
        await mark_run_running(session, message.run_id)

    # 模拟源、Elasticsearch、ClickHouse 都是同步客户端，这里统一丢到线程里执行。
    source_payload = await asyncio.to_thread(fetch_source_payload, message)
    article_rows = []
    search_documents = []
    metric_rows = []

    for item in source_payload.items:
        deduplicated = await mark_article_deduplicated(
            item.external_id,
            run_id=message.run_id,
            ttl_seconds=settings.article_dedupe_ttl_seconds,
        )
        if not deduplicated:
            continue

        published_at = parse_iso_datetime(item.published_at)
        content_hash = hashlib.sha256(item.content.encode("utf-8")).hexdigest()
        article_rows.append(
            {
                "external_id": item.external_id,
                "task_id": message.task_id,
                "run_id": message.run_id,
                "topic": item.topic,
                "source": item.source,
                "author": item.author,
                "title": item.title,
                "summary": item.summary,
                "content_hash": content_hash,
                "published_at": published_at,
            }
        )
        search_documents.append(
            {
                "external_id": item.external_id,
                "task_id": message.task_id,
                "run_id": message.run_id,
                "topic": item.topic,
                "source": item.source,
                "author": item.author,
                "title": item.title,
                "summary": item.summary,
                "content": item.content,
                "published_at": item.published_at,
            }
        )
        metric_rows.append(
            {
                "event_time": utcnow(),
                "task_id": message.task_id,
                "run_id": message.run_id,
                "article_external_id": item.external_id,
                "source": item.source,
                "topic": item.topic,
                "fetch_latency_ms": item.fetch_latency_ms,
                "body_length": len(item.content),
                "word_count": len(item.content.split()),
                "status": "indexed",
            }
        )

    indexed_count = await asyncio.to_thread(bulk_index_articles, search_documents)
    await asyncio.to_thread(insert_crawl_metrics, metric_rows)

    async with session_factory() as session:
        await upsert_article_metadata(session, article_rows)
        await finish_run(
            session=session,
            run_id=message.run_id,
            status="succeeded",
            fetched=len(source_payload.items),
            indexed=indexed_count,
        )

    if indexed_count > 0:
        await invalidate_search_cache(
            topics={document["topic"] for document in search_documents},
            sources={document["source"] for document in search_documents},
        )
    await record_worker_success(message.run_id)

    return {
        "run_id": message.run_id,
        "records_fetched": len(source_payload.items),
        "records_indexed": indexed_count,
    }


@celery_app.task(
    bind=True,
    name="app.tasks.crawl_tasks.execute_crawl_run",
    autoretry_for=(requests.RequestException,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=3,
)
def execute_crawl_run(self, message_payload: dict) -> dict:
    """Celery 任务入口：执行一次抓取、索引和分析写入。"""

    try:
        return asyncio.run(_execute_crawl_run_async(message_payload))
    except Exception as exc:
        message = CrawlMessage.model_validate(message_payload)
        logger.exception("Celery crawl task failed for run=%s", message.run_id)
        asyncio.run(record_worker_failure(message.run_id, str(exc)))

        async def _mark_failed() -> None:
            async with get_session_factory()() as session:
                await fail_run(session, message.run_id, str(exc))

        asyncio.run(_mark_failed())
        raise
