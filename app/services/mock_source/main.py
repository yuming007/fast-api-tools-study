from __future__ import annotations

from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

from fastapi import FastAPI, Query

from app.common.logging import configure_logging
from app.common.schemas import HealthResponse, SourceArticle, SourceBatchResponse
from app.common.time_utils import utcnow

logger = configure_logging("mock-source-service")

# 预设几个主题库，让模拟数据能覆盖不同的任务主题。
TOPIC_LIBRARY = {
    "ai": {
        "angles": [
            "LLM evaluation",
            "agent orchestration",
            "GPU cost control",
            "vector retrieval",
        ],
        "authors": ["Ada", "Lin", "Morgan", "Sam"],
    },
    "python": {
        "angles": [
            "FastAPI architecture",
            "async tracing",
            "type-driven APIs",
            "packaging workflows",
        ],
        "authors": ["Grace", "Taylor", "Alex", "Casey"],
    },
    "data": {
        "angles": [
            "stream ingestion",
            "columnar analytics",
            "search ranking",
            "cache consistency",
        ],
        "authors": ["Riley", "Jordan", "Avery", "Hayden"],
    },
}


def build_article(topic: str, task_id: int, run_id: int, index: int, stable: bool) -> SourceArticle:
    """按主题生成一篇模拟文章。"""

    library = TOPIC_LIBRARY.get(topic, TOPIC_LIBRARY["data"])
    angle = library["angles"][index % len(library["angles"])]
    author = library["authors"][index % len(library["authors"])]
    seed = f"{topic}-stable-{index}" if stable else f"{topic}-task-{task_id}-run-{run_id}-idx-{index}"
    external_id = str(uuid5(NAMESPACE_URL, seed))
    published_at = utcnow() - timedelta(minutes=(index + 1) * 7)
    title_prefix = "Persistent" if stable else "Fresh"
    title = f"{title_prefix} {topic.upper()} report on {angle}"
    summary = (
        f"{topic} pipeline article for task {task_id}, run {run_id}, "
        f"focused on {angle}."
    )
    content = (
        f"{title}. This article is produced by the mock source service to simulate "
        f"distributed crawling. It explains how {topic} teams reason about {angle}, "
        f"how they validate data quality, and how ingestion pipelines behave under "
        f"repeat scheduling. Stable records intentionally keep the same external id "
        f"so Redis deduplication can be observed in repeated runs."
    )
    return SourceArticle(
        external_id=external_id,
        topic=topic,
        source="mock-source",
        author=author,
        title=title,
        summary=summary,
        content=content,
        published_at=f"{published_at.isoformat()}Z",
        fetch_latency_ms=120 + index * 30 + (0 if stable else run_id % 5 * 15),
    )


app = FastAPI(
    title="mock-source-service",
    version="1.0.0",
)


@app.get("/health", response_model=HealthResponse)
async def healthcheck() -> HealthResponse:
    """模拟源服务健康检查。"""

    return HealthResponse(service="mock-source-service")


@app.get("/topics")
async def list_topics() -> dict:
    """查看当前支持的模拟主题。"""

    return {"topics": sorted(TOPIC_LIBRARY)}


@app.get("/feeds/articles", response_model=SourceBatchResponse)
async def generate_articles(
    topic: str = Query(default="ai"),
    batch: int = Query(default=5, ge=2, le=20),
    task_id: int = Query(default=0, ge=0),
    run_id: int = Query(default=0, ge=0),
) -> SourceBatchResponse:
    """返回一批模拟文章，其中部分文章会故意稳定重复，便于观察 Redis 去重。"""

    items = []
    stable_count = min(2, batch)
    for index in range(stable_count):
        items.append(build_article(topic, task_id, run_id, index, stable=True))
    for index in range(batch - stable_count):
        items.append(build_article(topic, task_id, run_id, index + stable_count, stable=False))

    return SourceBatchResponse(
        topic=topic,
        run_id=run_id,
        generated_at=utcnow(),
        items=items,
    )
