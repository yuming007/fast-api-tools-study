from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.common.bootstrap import bootstrap_dependencies
from app.common.config import get_settings
from app.common.logging import configure_logging
from app.common.redis_client import close_redis_client
from app.common.redis_state import get_worker_stats_snapshot
from app.common.schemas import HealthResponse, WorkerStats
from app.common.time_utils import parse_iso_datetime

settings = get_settings()
logger = configure_logging("worker-service")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 这个服务现在负责暴露 Celery worker 的观察接口。
    await bootstrap_dependencies(
        "worker-service",
        needs_redis=True,
        needs_rabbitmq=True,
    )
    try:
        yield
    finally:
        await close_redis_client()


app = FastAPI(
    title="worker-service",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def healthcheck() -> HealthResponse:
    """worker 观察服务健康检查。"""

    return HealthResponse(service="worker-service")


@app.get("/worker/stats", response_model=WorkerStats)
async def worker_stats() -> WorkerStats:
    """返回 Celery worker 最近一次执行统计。"""

    snapshot = await get_worker_stats_snapshot()
    return WorkerStats(
        status=snapshot.get("last_status", "idle"),
        queue=settings.rabbitmq_queue,
        processed_messages=int(snapshot.get("processed_messages", "0")),
        failed_messages=int(snapshot.get("failed_messages", "0")),
        last_run_id=int(snapshot["last_run_id"]) if snapshot.get("last_run_id") else None,
        last_message_at=parse_iso_datetime(snapshot.get("last_message_at")),
        last_error=snapshot.get("last_error") or None,
    )
