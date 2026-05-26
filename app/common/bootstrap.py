from __future__ import annotations

import asyncio

from app.common.clickhouse_client import ensure_clickhouse_schema, wait_for_clickhouse
from app.common.elasticsearch_client import ensure_articles_index, wait_for_elasticsearch
from app.common.logging import configure_logging
from app.common.mysql import init_mysql_schema, wait_for_mysql
from app.common.rabbitmq import ensure_topology, wait_for_rabbitmq
from app.common.redis_client import wait_for_redis


async def bootstrap_dependencies(
    service_name: str,
    *,
    needs_mysql: bool = False,
    needs_redis: bool = False,
    needs_rabbitmq: bool = False,
    needs_clickhouse: bool = False,
    needs_elasticsearch: bool = False,
):
    """在服务启动阶段按需检查和初始化各类基础设施。"""

    logger = configure_logging(service_name)

    if needs_mysql:
        await wait_for_mysql()
        await init_mysql_schema()
        logger.info("MySQL ready")

    if needs_redis:
        await wait_for_redis()
        logger.info("Redis ready")

    if needs_rabbitmq:
        await asyncio.to_thread(wait_for_rabbitmq)
        await asyncio.to_thread(ensure_topology)
        logger.info("RabbitMQ ready")

    if needs_clickhouse:
        await asyncio.to_thread(wait_for_clickhouse)
        await asyncio.to_thread(ensure_clickhouse_schema)
        logger.info("ClickHouse ready")

    if needs_elasticsearch:
        await asyncio.to_thread(wait_for_elasticsearch)
        await asyncio.to_thread(ensure_articles_index)
        logger.info("Elasticsearch ready")

    return logger
