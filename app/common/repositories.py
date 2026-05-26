from __future__ import annotations

from datetime import timedelta

from sqlalchemy import desc, func, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.models import Article, CrawlRun, CrawlTask
from app.common.schemas import TaskCreate
from app.common.time_utils import utcnow


async def create_task(session: AsyncSession, payload: TaskCreate) -> CrawlTask:
    """创建采集任务，并计算首次调度时间。"""

    next_run_at = None
    if payload.is_active and payload.schedule_seconds > 0:
        next_run_at = utcnow() + timedelta(seconds=payload.schedule_seconds)

    task = CrawlTask(
        name=payload.name,
        topic=payload.topic,
        schedule_seconds=payload.schedule_seconds,
        batch_size=payload.batch_size,
        source_path=payload.source_path,
        is_active=payload.is_active,
        next_run_at=next_run_at,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def list_tasks(session: AsyncSession) -> list[CrawlTask]:
    """按创建时间倒序返回全部任务。"""

    result = await session.scalars(select(CrawlTask).order_by(desc(CrawlTask.created_at)))
    return list(result.all())


async def get_task(session: AsyncSession, task_id: int) -> CrawlTask | None:
    """按主键查询任务。"""

    return await session.get(CrawlTask, task_id)


async def list_due_tasks(session: AsyncSession, limit: int = 20) -> list[CrawlTask]:
    """查询已到执行时间的任务。"""

    now = utcnow()
    query = (
        select(CrawlTask)
        .where(
            CrawlTask.is_active.is_(True),
            CrawlTask.schedule_seconds > 0,
            CrawlTask.next_run_at.is_not(None),
            CrawlTask.next_run_at <= now,
        )
        .order_by(CrawlTask.next_run_at.asc())
        .limit(limit)
    )
    result = await session.scalars(query)
    return list(result.all())


async def list_runs(session: AsyncSession, limit: int = 50) -> list[CrawlRun]:
    """返回最近的执行记录。"""

    result = await session.scalars(
        select(CrawlRun).order_by(desc(CrawlRun.dispatched_at)).limit(limit)
    )
    return list(result.all())


async def create_run(
    session: AsyncSession,
    task_id: int,
    trigger_source: str,
    source_batch: int,
) -> CrawlRun:
    """为一次调度或手动触发创建运行记录。"""

    run = CrawlRun(
        task_id=task_id,
        trigger_source=trigger_source,
        source_batch=source_batch,
        status="queued",
        dispatched_at=utcnow(),
    )
    session.add(run)
    # flush 会把 INSERT 发送给数据库，从而拿到 run.id，但事务还没提交。
    await session.flush()
    return run


async def mark_run_running(session: AsyncSession, run_id: int) -> CrawlRun | None:
    """把运行状态推进到 running。"""

    run = await session.get(CrawlRun, run_id)
    if run is None:
        return None
    run.status = "running"
    run.started_at = utcnow()
    await session.commit()
    await session.refresh(run)
    return run


async def finish_run(
    session: AsyncSession,
    run_id: int,
    status: str,
    fetched: int,
    indexed: int,
    error_message: str | None = None,
) -> CrawlRun | None:
    """统一收口运行结果，成功和失败都通过这个方法更新。"""

    run = await session.get(CrawlRun, run_id)
    if run is None:
        return None
    run.status = status
    run.records_fetched = fetched
    run.records_indexed = indexed
    run.error_message = error_message
    run.finished_at = utcnow()
    await session.commit()
    await session.refresh(run)
    return run


async def fail_run(session: AsyncSession, run_id: int, error_message: str) -> CrawlRun | None:
    """失败时写入错误信息，并把状态置为 failed。"""

    return await finish_run(
        session=session,
        run_id=run_id,
        status="failed",
        fetched=0,
        indexed=0,
        error_message=error_message[:4000],
    )


async def upsert_article_metadata(session: AsyncSession, rows: list[dict]) -> None:
    """把文章元数据写入 MySQL；如果已存在则更新。"""

    if not rows:
        return

    insert_stmt = mysql_insert(Article).values(rows)
    update_stmt = insert_stmt.on_duplicate_key_update(
        task_id=insert_stmt.inserted.task_id,
        run_id=insert_stmt.inserted.run_id,
        topic=insert_stmt.inserted.topic,
        source=insert_stmt.inserted.source,
        author=insert_stmt.inserted.author,
        title=insert_stmt.inserted.title,
        summary=insert_stmt.inserted.summary,
        content_hash=insert_stmt.inserted.content_hash,
        published_at=insert_stmt.inserted.published_at,
        updated_at=utcnow(),
    )
    # 使用 MySQL 的 upsert 语义，避免重复文章插入时报唯一键冲突。
    await session.execute(update_stmt)
    await session.commit()


async def count_active_tasks(session: AsyncSession) -> int:
    """统计当前启用中的任务数量。"""

    return int(
        await session.scalar(
            select(func.count(CrawlTask.id)).where(CrawlTask.is_active.is_(True))
        )
        or 0
    )


async def list_next_tasks(session: AsyncSession, limit: int = 5) -> list[CrawlTask]:
    """返回最近将要执行的任务，方便调试调度器状态。"""

    query = (
        select(CrawlTask)
        .where(CrawlTask.is_active.is_(True), CrawlTask.next_run_at.is_not(None))
        .order_by(CrawlTask.next_run_at.asc())
        .limit(limit)
    )
    result = await session.scalars(query)
    return list(result.all())


async def seed_demo_tasks(session: AsyncSession) -> list[CrawlTask]:
    """初始化演示任务，避免空项目启动后没有可观察的数据链路。"""

    existing_count = int(await session.scalar(select(func.count(CrawlTask.id))) or 0)
    if existing_count > 0:
        return await list_tasks(session)

    payloads = [
        TaskCreate(
            name="AI Weekly Signals",
            topic="ai",
            schedule_seconds=30,
            batch_size=6,
            source_path="/feeds/articles",
            is_active=True,
        ),
        TaskCreate(
            name="Python Service Digest",
            topic="python",
            schedule_seconds=45,
            batch_size=5,
            source_path="/feeds/articles",
            is_active=True,
        ),
        TaskCreate(
            name="Data Infra Watch",
            topic="data",
            schedule_seconds=60,
            batch_size=5,
            source_path="/feeds/articles",
            is_active=True,
        ),
    ]
    tasks = []
    for payload in payloads:
        # 逐条创建，保持逻辑直观，方便学习 ORM 的任务写入流程。
        tasks.append(await create_task(session, payload))
    return tasks
