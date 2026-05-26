from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.common.config import get_settings
from app.common.models import Base

_engine: AsyncEngine | None = None

# 这是会话工厂，绑定了带连接池的异步 engine。
# 每次调用 `AsyncSessionLocal()` 都会创建一个新的逻辑会话。
AsyncSessionLocal: sessionmaker | None = None


def get_engine() -> AsyncEngine:
    """创建并缓存异步 MySQL 引擎。"""

    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.mysql_dsn,
            future=True,
            pool_pre_ping=True,
            pool_size=settings.mysql_pool_size,
            max_overflow=settings.mysql_max_overflow,
            pool_recycle=settings.mysql_pool_recycle_seconds,
            pool_timeout=settings.mysql_pool_timeout_seconds,
        )
    return _engine


def get_session_factory() -> sessionmaker:
    """返回全局唯一的 AsyncSession 工厂。"""

    global AsyncSessionLocal
    if AsyncSessionLocal is None:
        AsyncSessionLocal = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI 依赖注入入口。

    每个请求都会创建一个全新的 AsyncSession。
    请求结束后关闭 session，并把底层连接归还给连接池。
    """

    async with get_session_factory()() as session:
        try:
            yield session
        finally:
            # 请求结束后关闭逻辑会话，并把底层连接归还给连接池。
            await session.close()


async def wait_for_mysql(max_attempts: int = 60, delay_seconds: float = 2.0) -> None:
    """在服务启动阶段轮询 MySQL，直到数据库可连接。"""

    engine = get_engine()
    for attempt in range(1, max_attempts + 1):
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            return
        except Exception:
            if attempt == max_attempts:
                raise
            await asyncio.sleep(delay_seconds)


async def init_mysql_schema() -> None:
    """使用异步 engine 初始化 ORM 映射出的表结构。"""

    async with get_engine().begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
