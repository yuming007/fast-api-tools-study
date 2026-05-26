from __future__ import annotations

from celery import Celery
from kombu import Exchange, Queue

from app.common.config import get_settings

settings = get_settings()

# 使用 RabbitMQ 作为 Celery broker，用 Redis 保存任务执行结果和状态。
broker_url = (
    f"amqp://{settings.rabbitmq_user}:{settings.rabbitmq_password}"
    f"@{settings.rabbitmq_host}:{settings.rabbitmq_port}{settings.rabbitmq_vhost}"
)

celery_app = Celery(
    "fast_api_tools_study",
    broker=broker_url,
    backend=settings.redis_celery_result_backend_url,
)

default_exchange = Exchange(settings.rabbitmq_exchange, type="direct", durable=True)

celery_app.conf.update(
    task_default_exchange=settings.rabbitmq_exchange,
    task_default_exchange_type="direct",
    task_default_routing_key=settings.rabbitmq_routing_key,
    task_default_queue=settings.rabbitmq_queue,
    task_queues=(
        Queue(
            settings.rabbitmq_queue,
            exchange=default_exchange,
            routing_key=settings.rabbitmq_routing_key,
            durable=True,
        ),
        Queue(
            settings.rabbitmq_scheduler_queue,
            exchange=default_exchange,
            routing_key=settings.rabbitmq_scheduler_routing_key,
            durable=True,
        ),
    ),
    task_routes={
        "app.tasks.crawl_tasks.execute_crawl_run": {
            "queue": settings.rabbitmq_queue,
            "routing_key": settings.rabbitmq_routing_key,
        },
        "app.tasks.scheduler_tasks.run_scheduler_scan": {
            "queue": settings.rabbitmq_scheduler_queue,
            "routing_key": settings.rabbitmq_scheduler_routing_key,
        },
    },
    task_track_started=True,
    task_time_limit=settings.celery_task_time_limit_seconds,
    task_soft_time_limit=settings.celery_task_soft_time_limit_seconds,
    result_expires=settings.celery_result_expires_seconds,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    timezone="UTC",
    beat_schedule={
        "scheduler-scan": {
            "task": "app.tasks.scheduler_tasks.run_scheduler_scan",
            "schedule": settings.scheduler_poll_seconds,
        }
    },
)

# 自动发现 Celery 任务模块。
celery_app.autodiscover_tasks(["app.tasks"])
