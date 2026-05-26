from __future__ import annotations

import asyncio

from redis import asyncio as redis

from app.common.config import get_settings

_redis_client: redis.Redis | None = None


def get_redis_client() -> redis.Redis:
    """创建并缓存异步 Redis 客户端。"""

    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


async def close_redis_client() -> None:
    """在进程退出前关闭 Redis 客户端，避免连接悬挂。"""

    global _redis_client
    if _redis_client is None:
        return
    await _redis_client.aclose()
    _redis_client = None


async def wait_for_redis(max_attempts: int = 60, delay_seconds: float = 1.0) -> None:
    """在启动阶段等待 Redis 就绪。"""

    client = get_redis_client()
    for attempt in range(1, max_attempts + 1):
        try:
            await client.ping()
            return
        except Exception:
            if attempt == max_attempts:
                raise
            await asyncio.sleep(delay_seconds)
