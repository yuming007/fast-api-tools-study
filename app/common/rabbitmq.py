from __future__ import annotations

import time

import pika

from app.common.config import get_settings


def get_connection_parameters() -> pika.ConnectionParameters:
    """根据统一配置构造 RabbitMQ 连接参数。"""

    settings = get_settings()
    credentials = pika.PlainCredentials(settings.rabbitmq_user, settings.rabbitmq_password)
    return pika.ConnectionParameters(
        host=settings.rabbitmq_host,
        port=settings.rabbitmq_port,
        virtual_host=settings.rabbitmq_vhost,
        credentials=credentials,
        heartbeat=60,
        blocked_connection_timeout=30,
    )


def declare_topology(channel: pika.adapters.blocking_connection.BlockingChannel) -> None:
    """声明 Celery 依赖的交换机、执行队列和调度队列。"""

    settings = get_settings()
    channel.exchange_declare(
        exchange=settings.rabbitmq_exchange,
        exchange_type="direct",
        durable=True,
    )
    channel.queue_declare(queue=settings.rabbitmq_queue, durable=True)
    channel.queue_bind(
        queue=settings.rabbitmq_queue,
        exchange=settings.rabbitmq_exchange,
        routing_key=settings.rabbitmq_routing_key,
    )
    channel.queue_declare(queue=settings.rabbitmq_scheduler_queue, durable=True)
    channel.queue_bind(
        queue=settings.rabbitmq_scheduler_queue,
        exchange=settings.rabbitmq_exchange,
        routing_key=settings.rabbitmq_scheduler_routing_key,
    )


def wait_for_rabbitmq(max_attempts: int = 60, delay_seconds: float = 2.0) -> None:
    """在启动阶段轮询 RabbitMQ 直到可连接。"""

    for attempt in range(1, max_attempts + 1):
        try:
            connection = pika.BlockingConnection(get_connection_parameters())
            connection.close()
            return
        except Exception:
            if attempt == max_attempts:
                raise
            time.sleep(delay_seconds)


def ensure_topology() -> None:
    """确保 RabbitMQ 拓扑已创建。"""

    connection = pika.BlockingConnection(get_connection_parameters())
    try:
        channel = connection.channel()
        declare_topology(channel)
    finally:
        connection.close()
