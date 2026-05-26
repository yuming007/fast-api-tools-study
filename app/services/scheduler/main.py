from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.common.bootstrap import bootstrap_dependencies
from app.common.celery_app import celery_app
from app.common.config import get_settings
from app.common.logging import configure_logging
from app.common.mysql import get_session_factory
from app.common.redis_client import close_redis_client
from app.common.redis_state import get_scheduler_state_snapshot, record_scheduler_enqueue
from app.common.repositories import count_active_tasks, list_next_tasks
from app.common.schemas import HealthResponse, SchedulerState, TaskRead
from app.common.time_utils import parse_iso_datetime, utcnow

settings = get_settings()
logger = configure_logging("scheduler-service")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 调度服务负责观察调度状态，并提供手动触发 Celery scan 的接口。
    await bootstrap_dependencies(
        "scheduler-service",
        needs_mysql=True,
        needs_redis=True,
        needs_rabbitmq=True,
    )
    try:
        yield
    finally:
        await close_redis_client()


app = FastAPI(
    title="scheduler-service",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def healthcheck() -> HealthResponse:
    """调度服务健康检查。"""

    return HealthResponse(service="scheduler-service")


@app.post("/scheduler/tick")
async def trigger_cycle() -> dict:
    """手动投递一轮 Celery 调度扫描任务。"""

    result = await asyncio.to_thread(
        celery_app.send_task,
        "app.tasks.scheduler_tasks.run_scheduler_scan",
        queue=settings.rabbitmq_scheduler_queue,
        routing_key=settings.rabbitmq_scheduler_routing_key,
    )
    await record_scheduler_enqueue(result.id)
    return {
        "status": "ok",
        "celery_task_id": result.id,
        "at": utcnow().isoformat(),
    }


@app.get("/scheduler/state", response_model=SchedulerState)
async def scheduler_state() -> SchedulerState:
    """查看调度器状态与下一批待执行任务。"""

    state_snapshot = await get_scheduler_state_snapshot()
    session_factory = get_session_factory()
    async with session_factory() as session:
        active_tasks = await count_active_tasks(session)
        next_records = await list_next_tasks(session)
        next_tasks = [TaskRead.model_validate(task) for task in next_records]

    last_dispatched_raw = state_snapshot.get("last_dispatched_run_ids", "[]")
    try:
        last_dispatched_run_ids = list(json.loads(last_dispatched_raw))
    except json.JSONDecodeError:
        last_dispatched_run_ids = []

    return SchedulerState(
        status="running",
        poll_seconds=settings.scheduler_poll_seconds,
        cycles=int(state_snapshot.get("cycles", "0")),
        last_cycle_at=parse_iso_datetime(state_snapshot.get("last_cycle_at")),
        last_dispatched_run_ids=last_dispatched_run_ids,
        active_tasks=active_tasks,
        next_tasks=next_tasks,
    )
