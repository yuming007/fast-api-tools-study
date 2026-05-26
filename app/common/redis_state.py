from __future__ import annotations

import asyncio
import hashlib
import json
import random
from collections.abc import Iterable
from uuid import uuid4

from app.common.config import get_settings
from app.common.redis_client import get_redis_client
from app.common.time_utils import utcnow


def build_redis_key(*parts: object) -> str:
    """统一构造带命名空间的 Redis key。"""

    settings = get_settings()
    normalized = [str(part) for part in parts]
    return ":".join([settings.redis_namespace, *normalized])


def manual_dispatch_key(task_id: int) -> str:
    """手动触发限流 key。"""

    return build_redis_key("lock", "manual-dispatch", task_id)


def schedule_lock_key(task_id: int) -> str:
    """调度防重锁 key。"""

    return build_redis_key("lock", "schedule", task_id)


def article_dedupe_key(external_id: str) -> str:
    """文章去重 key。"""

    return build_redis_key("dedupe", "article", external_id)


def search_version_key(scope: str, value: str) -> str:
    """搜索缓存版本 key。"""

    return build_redis_key("search", "version", scope, value)


def search_cache_lock_key(cache_key: str) -> str:
    """搜索缓存重建锁 key。"""

    cache_digest = hashlib.sha1(cache_key.encode("utf-8")).hexdigest()
    return build_redis_key("lock", "search-cache-rebuild", cache_digest)


def worker_stats_key() -> str:
    """Celery worker 统计 key。"""

    return build_redis_key("worker", "stats")


def scheduler_state_key() -> str:
    """调度状态 key。"""

    return build_redis_key("scheduler", "state")


async def try_set_with_ttl(key: str, value: str, ttl_seconds: int) -> bool:
    """尝试写入一个带 TTL 的 key，常用于轻量级限流和去重。"""

    client = get_redis_client()
    return bool(await client.set(key, value, ex=ttl_seconds, nx=True))


async def acquire_lock(key: str, ttl_seconds: int) -> str | None:
    """获取带 token 的分布式锁。"""

    token = uuid4().hex
    locked = await try_set_with_ttl(key, token, ttl_seconds)
    return token if locked else None


async def release_lock(key: str, token: str) -> bool:
    """使用 Lua 脚本按 token 安全释放锁。"""

    client = get_redis_client()
    released = await client.eval(
        """
        if redis.call('get', KEYS[1]) == ARGV[1] then
            return redis.call('del', KEYS[1])
        end
        return 0
        """,
        1,
        key,
        token,
    )
    return bool(released)


async def mark_article_deduplicated(external_id: str, run_id: int, ttl_seconds: int) -> bool:
    """标记文章已经处理过；如果已存在则返回 False。"""

    return await try_set_with_ttl(article_dedupe_key(external_id), str(run_id), ttl_seconds)


async def get_search_version_bundle(topic: str | None, source: str | None) -> tuple[int, int, int]:
    """获取构造搜索缓存 key 所需的全局/主题/来源版本号。"""

    client = get_redis_client()
    keys = [
        search_version_key("global", "all"),
        search_version_key("topic", topic or "all"),
        search_version_key("source", source or "all"),
    ]
    versions = await client.mget(keys)
    return tuple(int(value or 0) for value in versions)


async def build_search_cache_key(
    q: str | None,
    topic: str | None,
    source: str | None,
    size: int,
) -> str:
    """构造更细粒度的搜索缓存 key。"""

    global_version, topic_version, source_version = await get_search_version_bundle(topic, source)
    payload = json.dumps(
        {
            "q": q or "",
            "topic": topic or "",
            "source": source or "",
            "size": size,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    fingerprint = hashlib.sha1(payload.encode("utf-8")).hexdigest()
    version_parts = []
    # 只有“无 topic 且无 source 过滤”的全局查询才依赖 global 版本号，
    # 这样局部查询不会因为其他主题的数据变化被整体打掉缓存。
    if topic is None and source is None:
        version_parts.append(f"g{global_version}")
    version_parts.append(f"t{topic_version}" if topic else "t*")
    version_parts.append(f"s{source_version}" if source else "s*")
    return build_redis_key(
        "search",
        "cache",
        *version_parts,
        fingerprint,
    )


async def invalidate_search_cache(topics: Iterable[str], sources: Iterable[str]) -> None:
    """按全局、主题、来源三个层级推进搜索缓存版本。"""

    client = get_redis_client()
    unique_topics = sorted({topic for topic in topics if topic})
    unique_sources = sorted({source for source in sources if source})
    async with client.pipeline(transaction=False) as pipeline:
        pipeline.incr(search_version_key("global", "all"))
        for topic in unique_topics:
            pipeline.incr(search_version_key("topic", topic))
        for source in unique_sources:
            pipeline.incr(search_version_key("source", source))
        await pipeline.execute()


async def set_cache_value(key: str, value: str, ttl_seconds: int) -> None:
    """写入缓存时加一点 TTL 抖动，降低同一时刻集中过期的概率。"""

    client = get_redis_client()
    jitter_window = max(0, ttl_seconds // 10)
    ttl_with_jitter = ttl_seconds + (random.randint(0, jitter_window) if jitter_window > 0 else 0)
    await client.set(key, value, ex=ttl_with_jitter)


async def wait_for_cached_value(
    key: str,
    timeout_ms: int,
    interval_ms: int = 50,
) -> str | None:
    """等待其他请求完成缓存重建，减少缓存击穿时的重复回源。"""

    client = get_redis_client()
    deadline = asyncio.get_running_loop().time() + (timeout_ms / 1000)
    while asyncio.get_running_loop().time() < deadline:
        cached = await client.get(key)
        if cached is not None:
            return cached
        await asyncio.sleep(interval_ms / 1000)
    return await client.get(key)


async def record_worker_success(run_id: int) -> None:
    """记录 Celery worker 成功处理任务的统计。"""

    client = get_redis_client()
    now = utcnow().isoformat()
    async with client.pipeline(transaction=False) as pipeline:
        pipeline.hincrby(worker_stats_key(), "processed_messages", 1)
        pipeline.hset(
            worker_stats_key(),
            mapping={
                "last_run_id": run_id,
                "last_message_at": now,
                "last_status": "succeeded",
                "last_error": "",
            },
        )
        await pipeline.execute()


async def record_worker_failure(run_id: int | None, error_message: str) -> None:
    """记录 Celery worker 处理失败的统计。"""

    client = get_redis_client()
    now = utcnow().isoformat()
    mapping = {
        "last_message_at": now,
        "last_status": "failed",
        "last_error": error_message[:1000],
    }
    if run_id is not None:
        mapping["last_run_id"] = str(run_id)
    async with client.pipeline(transaction=False) as pipeline:
        pipeline.hincrby(worker_stats_key(), "failed_messages", 1)
        pipeline.hset(worker_stats_key(), mapping=mapping)
        await pipeline.execute()


async def get_worker_stats_snapshot() -> dict[str, str]:
    """读取 worker 统计快照。"""

    client = get_redis_client()
    return await client.hgetall(worker_stats_key())


async def record_scheduler_enqueue(celery_task_id: str) -> None:
    """记录最近一次调度扫描任务的 Celery task id。"""

    client = get_redis_client()
    await client.hset(
        scheduler_state_key(),
        mapping={
            "last_celery_task_id": celery_task_id,
            "last_enqueue_at": utcnow().isoformat(),
        },
    )


async def record_scheduler_cycle(dispatched_run_ids: list[int], error_message: str | None = None) -> None:
    """记录一轮调度扫描的结果。"""

    client = get_redis_client()
    mapping = {
        "last_cycle_at": utcnow().isoformat(),
        "last_dispatched_run_ids": json.dumps(dispatched_run_ids),
        "last_status": "failed" if error_message else "succeeded",
        "last_error": (error_message or "")[:1000],
    }
    async with client.pipeline(transaction=False) as pipeline:
        pipeline.hincrby(scheduler_state_key(), "cycles", 1)
        pipeline.hset(scheduler_state_key(), mapping=mapping)
        await pipeline.execute()


async def get_scheduler_state_snapshot() -> dict[str, str]:
    """读取调度状态快照。"""

    client = get_redis_client()
    return await client.hgetall(scheduler_state_key())
