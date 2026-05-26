import asyncio

from app.common.bootstrap import bootstrap_dependencies
from app.common.logging import configure_logging
from app.common.mysql import get_session_factory
from app.common.redis_client import close_redis_client
from app.common.repositories import seed_demo_tasks


logger = configure_logging("bootstrap")


async def main() -> None:
    """初始化所有基础设施，并在首次启动时写入演示任务。"""

    try:
        await bootstrap_dependencies(
            "bootstrap",
            needs_mysql=True,
            needs_redis=True,
            needs_rabbitmq=True,
            needs_clickhouse=True,
            needs_elasticsearch=True,
        )
        session_factory = get_session_factory()
        async with session_factory() as session:
            # 首次启动时写入默认演示任务，便于直接观察调度链路。
            tasks = await seed_demo_tasks(session)
            logger.info("Seeded or loaded %s demo tasks", len(tasks))
    finally:
        await close_redis_client()


if __name__ == "__main__":
    asyncio.run(main())
