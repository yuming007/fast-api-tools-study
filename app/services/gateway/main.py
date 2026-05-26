from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.bootstrap import bootstrap_dependencies
from app.common.config import get_settings
from app.common.dispatching import dispatch_task
from app.common.logging import configure_logging
from app.common.mysql import get_db
from app.common.redis_client import close_redis_client
from app.common.redis_state import acquire_lock, manual_dispatch_key, release_lock
from app.common.repositories import create_task, get_task, list_runs, list_tasks
from app.common.schemas import DispatchResponse, HealthResponse, RunRead, TaskCreate, TaskRead

settings = get_settings()
logger = configure_logging("gateway-service")

# 通过依赖注入为每个请求分配一个独立的 AsyncSession。
SessionDep = Annotated[AsyncSession, Depends(get_db)]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 服务启动时先确保依赖可用，这样请求进来时不会撞到半初始化状态。
    await bootstrap_dependencies(
        "gateway-service",
        needs_mysql=True,
        needs_redis=True,
        needs_rabbitmq=True,
    )
    try:
        yield
    finally:
        await close_redis_client()


app = FastAPI(
    title="gateway-service",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def healthcheck() -> HealthResponse:
    """提供最基础的健康检查接口。"""

    return HealthResponse(service="gateway-service")


@app.post("/tasks", response_model=TaskRead, status_code=201)
async def create_task_endpoint(payload: TaskCreate, session: SessionDep) -> TaskRead:
    """创建新的采集任务。"""

    task = await create_task(session, payload)
    return TaskRead.model_validate(task)


@app.get("/tasks", response_model=list[TaskRead])
async def list_tasks_endpoint(session: SessionDep) -> list[TaskRead]:
    """查询当前所有采集任务。"""

    tasks = await list_tasks(session)
    return [TaskRead.model_validate(task) for task in tasks]


@app.get("/runs", response_model=list[RunRead])
async def list_runs_endpoint(session: SessionDep, limit: int = 20) -> list[RunRead]:
    """查询最近的任务运行记录。"""

    limit = max(1, min(limit, 100))
    runs = await list_runs(session, limit=limit)
    return [RunRead.model_validate(run) for run in runs]


@app.post("/tasks/{task_id}/dispatch", response_model=DispatchResponse)
async def dispatch_task_endpoint(task_id: int, session: SessionDep) -> DispatchResponse:
    """手动触发一个任务，并把执行消息投递到 Celery。"""

    task = await get_task(session, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    lock_key = manual_dispatch_key(task_id)
    token = await acquire_lock(lock_key, ttl_seconds=settings.manual_dispatch_throttle_seconds)
    # 这里用 Redis 做带 token 的限流锁，避免重复点击或误删别人的锁。
    if token is None:
        raise HTTPException(status_code=409, detail="Task dispatch was throttled by Redis")

    try:
        run, celery_result = await dispatch_task(
            session=session,
            task=task,
            trigger_source="manual",
            advance_schedule=False,
        )
    except Exception as exc:
        logger.exception("Manual dispatch failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await release_lock(lock_key, token)

    return DispatchResponse(
        run_id=run.id,
        celery_task_id=celery_result.id,
        status=run.status,
        detail="Task queued to Celery via RabbitMQ",
    )
