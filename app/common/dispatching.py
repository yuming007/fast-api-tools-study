from __future__ import annotations

import asyncio
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.celery_app import celery_app
from app.common.models import CrawlTask
from app.common.repositories import create_run, fail_run
from app.common.schemas import CrawlMessage
from app.common.time_utils import utcnow


async def dispatch_task(
    session: AsyncSession,
    task: CrawlTask,
    trigger_source: str,
    advance_schedule: bool,
):
    """把任务状态推进到已分发，并向 Celery 投递执行消息。"""

    dispatched_at = utcnow()
    run = await create_run(
        session=session,
        task_id=task.id,
        trigger_source=trigger_source,
        source_batch=task.batch_size,
    )
    task.last_dispatched_at = dispatched_at
    if advance_schedule and task.schedule_seconds > 0:
        # 调度模式下要顺便推进下一次执行时间；手动触发则不推进。
        task.next_run_at = dispatched_at + timedelta(seconds=task.schedule_seconds)
    await session.commit()
    await session.refresh(run)

    message = CrawlMessage(
        task_id=task.id,
        run_id=run.id,
        topic=task.topic,
        batch_size=task.batch_size,
        source_path=task.source_path,
        trigger_source=trigger_source,
        dispatched_at=dispatched_at,
    )

    try:
        # `send_task` 底层会访问 broker，这里放到线程里，避免阻塞 FastAPI 事件循环。
        celery_result = await asyncio.to_thread(
            celery_app.send_task,
            "app.tasks.crawl_tasks.execute_crawl_run",
            kwargs={"message_payload": message.model_dump(mode="json")},
            queue=task_queue_name(),
            routing_key=task_routing_key(),
        )
    except Exception as exc:
        await fail_run(session, run.id, f"RabbitMQ publish failed: {exc}")
        raise

    return run, celery_result


def task_queue_name() -> str:
    """返回 Celery 默认执行队列名。"""

    from app.common.config import get_settings

    return get_settings().rabbitmq_queue


def task_routing_key() -> str:
    """返回 Celery 默认执行路由键。"""

    from app.common.config import get_settings

    return get_settings().rabbitmq_routing_key
