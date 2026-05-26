from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """项目的统一配置入口。"""

    # 这里统一从环境变量读取配置，避免把地址和密码散落到各个服务里。
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "fast-api-tools-study"
    log_level: str = "INFO"

    mysql_host: str = "mysql"
    mysql_port: int = 3306
    mysql_user: str = "study"
    mysql_password: str = "study"
    mysql_db: str = "crawler"
    mysql_pool_size: int = 10
    mysql_max_overflow: int = 20
    mysql_pool_recycle_seconds: int = 1800
    mysql_pool_timeout_seconds: int = 30

    redis_url: str = "redis://redis:6379/0"
    redis_celery_result_backend_url: str = "redis://redis:6379/1"
    redis_namespace: str = "study"

    rabbitmq_host: str = "rabbitmq"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "study"
    rabbitmq_password: str = "study"
    rabbitmq_vhost: str = "/"
    rabbitmq_exchange: str = "study.tasks"
    rabbitmq_queue: str = "crawl.jobs"
    rabbitmq_routing_key: str = "crawl.execute"
    rabbitmq_scheduler_queue: str = "scheduler.jobs"
    rabbitmq_scheduler_routing_key: str = "scheduler.scan"

    clickhouse_host: str = "clickhouse"
    clickhouse_port: int = 8123
    clickhouse_user: str = "study"
    clickhouse_password: str = "study"
    clickhouse_db: str = "crawler_analytics"

    elasticsearch_url: str = "http://elasticsearch:9200"
    elasticsearch_index: str = "articles"

    mock_source_base_url: str = "http://mock-source:8004"

    search_cache_ttl_seconds: int = 90
    search_cache_rebuild_lock_seconds: int = 8
    search_cache_wait_timeout_ms: int = 250
    article_dedupe_ttl_seconds: int = 600
    scheduler_poll_seconds: int = 15
    request_timeout_seconds: int = 15
    manual_dispatch_throttle_seconds: int = 5
    celery_task_time_limit_seconds: int = 180
    celery_task_soft_time_limit_seconds: int = 120
    celery_result_expires_seconds: int = 3600
    celery_worker_concurrency: int = 4

    default_search_size: int = Field(default=10, ge=1, le=50)

    @property
    def mysql_dsn(self) -> str:
        # 使用 asyncmy 驱动，让 FastAPI 和 SQLAlchemy 以异步方式访问 MySQL。
        return (
            f"mysql+asyncmy://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_db}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """缓存配置对象，避免在每次导入时重复解析环境变量。"""

    return Settings()
