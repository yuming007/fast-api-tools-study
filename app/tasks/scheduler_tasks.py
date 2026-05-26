from __future__ import annotations

import asyncio

from app.common.celery_app import celery_app
from app.common.dispatching import dispatch_task
from app.common.logging import configure_logging
from app.common.mysql import get_session_factory
from app.common.redis_state import acquire_lock, record_scheduler_cycle, release_lock, schedule_lock_key
from app.common.repositories import list_due_tasks

logger = configure_logging("celery-scheduler-worker")


async def _run_scheduler_scan_async() -> dict:
    """异步执行一轮调度扫描，并把到期任务投递给 Celery。"""

    dispatched_run_ids: list[int] = []
    session_factory = get_session_factory()

    async with session_factory() as session:
        due_tasks = await list_due_tasks(session, limit=20)
        for task in due_tasks:
            lock_key = schedule_lock_key(task.id)
            token = await acquire_lock(lock_key, ttl_seconds=20)
            if not token:
                continue
            try:
                run, _celery_result = await dispatch_task(
                    session=session,
                    task=task,
                    trigger_source="scheduler",
                    advance_schedule=True,
                )
                dispatched_run_ids.append(run.id)
            except Exception:
                logger.exception("Scheduled dispatch failed for task=%s", task.id)
            finally:
                await release_lock(lock_key, token)

    await record_scheduler_cycle(dispatched_run_ids)
    return {
        "dispatched_run_ids": dispatched_run_ids,
        "count": len(dispatched_run_ids),
    }


@celery_app.task(
    bind=True,
    name="app.tasks.scheduler_tasks.run_scheduler_scan",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=30,
    retry_jitter=True,
    max_retries=2,
)
def run_scheduler_scan(self) -> dict:
    """Celery Beat 定期触发的扫描任务。"""

    try:
        return asyncio.run(_run_scheduler_scan_async())
    except Exception as exc:
        logger.exception("Scheduler scan task failed")
        asyncio.run(record_scheduler_cycle([], error_message=str(exc)))
        raise
