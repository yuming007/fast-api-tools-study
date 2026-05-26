from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.common.time_utils import utcnow


class Base(DeclarativeBase):
    """所有 ORM 模型的共同基类。"""

    pass


class CrawlTask(Base):
    """采集任务表，记录任务配置和调度状态。"""

    __tablename__ = "crawl_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    topic: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    schedule_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    batch_size: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    source_path: Mapped[str] = mapped_column(String(128), nullable=False, default="/feeds/articles")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_dispatched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )


class CrawlRun(Base):
    """任务运行表，记录每次执行的状态与结果。"""

    __tablename__ = "crawl_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    trigger_source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    source_batch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_indexed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    dispatched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )


class Article(Base):
    """文章元数据表，只存结构化字段，不存全文正文。"""

    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    task_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    run_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    author: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
