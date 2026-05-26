from __future__ import annotations

import time
from typing import Any

import clickhouse_connect

from app.common.config import get_settings

_clients: dict[str, Any] = {}


def get_clickhouse_client(database: str | None = None):
    """按数据库维度缓存 ClickHouse 客户端。"""

    settings = get_settings()
    target_database = database or settings.clickhouse_db
    cache_key = target_database or "__default__"
    if cache_key not in _clients:
        kwargs = {
            "host": settings.clickhouse_host,
            "port": settings.clickhouse_port,
            "username": settings.clickhouse_user,
            "password": settings.clickhouse_password,
        }
        if target_database:
            kwargs["database"] = target_database
        _clients[cache_key] = clickhouse_connect.get_client(**kwargs)
    return _clients[cache_key]


def wait_for_clickhouse(max_attempts: int = 60, delay_seconds: float = 2.0) -> None:
    """在启动阶段等待 ClickHouse 可执行查询。"""

    for attempt in range(1, max_attempts + 1):
        try:
            get_clickhouse_client(database=None).command("SELECT 1")
            return
        except Exception:
            if attempt == max_attempts:
                raise
            time.sleep(delay_seconds)


def ensure_clickhouse_schema() -> None:
    """初始化 ClickHouse 数据库和分析表。"""

    settings = get_settings()
    root_client = get_clickhouse_client(database=None)
    root_client.command(f"CREATE DATABASE IF NOT EXISTS {settings.clickhouse_db}")
    analytics_client = get_clickhouse_client(settings.clickhouse_db)
    analytics_client.command(
        """
        CREATE TABLE IF NOT EXISTS crawl_metrics (
            event_time DateTime,
            task_id UInt64,
            run_id UInt64,
            article_external_id String,
            source String,
            topic String,
            fetch_latency_ms UInt32,
            body_length UInt32,
            word_count UInt32,
            status LowCardinality(String)
        )
        ENGINE = MergeTree
        PARTITION BY toDate(event_time)
        ORDER BY (task_id, run_id, event_time)
        """
    )


def insert_crawl_metrics(rows: list[dict[str, Any]]) -> None:
    """批量写入采集分析事件。"""

    if not rows:
        return

    client = get_clickhouse_client()
    ordered_rows = [
        [
            row["event_time"],
            row["task_id"],
            row["run_id"],
            row["article_external_id"],
            row["source"],
            row["topic"],
            row["fetch_latency_ms"],
            row["body_length"],
            row["word_count"],
            row["status"],
        ]
        for row in rows
    ]
    client.insert(
        "crawl_metrics",
        ordered_rows,
        column_names=[
            "event_time",
            "task_id",
            "run_id",
            "article_external_id",
            "source",
            "topic",
            "fetch_latency_ms",
            "body_length",
            "word_count",
            "status",
        ],
    )
