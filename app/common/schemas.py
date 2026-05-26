from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    """统一健康检查响应。"""

    service: str
    status: str = "ok"


class TaskCreate(BaseModel):
    """创建任务时的请求体。"""

    name: str = Field(..., min_length=3, max_length=120)
    topic: str = Field(..., min_length=2, max_length=64)
    schedule_seconds: int = Field(default=60, ge=0, le=86400)
    batch_size: int = Field(default=5, ge=2, le=20)
    source_path: str = Field(default="/feeds/articles", pattern=r"^/")
    is_active: bool = True


class TaskRead(BaseModel):
    """任务详情响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    topic: str
    schedule_seconds: int
    batch_size: int
    source_path: str
    is_active: bool
    last_dispatched_at: datetime | None
    next_run_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RunRead(BaseModel):
    """任务运行记录响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    trigger_source: str
    status: str
    source_batch: int
    records_fetched: int
    records_indexed: int
    error_message: str | None
    dispatched_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class DispatchResponse(BaseModel):
    """手动触发后的响应体。"""

    run_id: int
    celery_task_id: str
    status: str
    detail: str


class CrawlMessage(BaseModel):
    """RabbitMQ 中传递的采集任务消息。"""

    task_id: int
    run_id: int
    topic: str
    batch_size: int
    source_path: str
    trigger_source: str
    dispatched_at: datetime


class SourceArticle(BaseModel):
    """模拟数据源返回的一篇文章。"""

    external_id: str
    topic: str
    source: str
    author: str
    title: str
    summary: str
    content: str
    published_at: str
    fetch_latency_ms: int


class SourceBatchResponse(BaseModel):
    """模拟数据源一次返回的一批文章。"""

    topic: str
    run_id: int
    generated_at: datetime
    items: list[SourceArticle]


class SearchHit(BaseModel):
    """全文检索中的单条命中结果。"""

    external_id: str
    task_id: int
    run_id: int
    topic: str
    source: str
    author: str
    title: str
    summary: str
    published_at: str | None
    highlight: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    """全文检索响应。"""

    cached: bool
    total: int
    hits: list[SearchHit]


class TrendPoint(BaseModel):
    """趋势分析中的时间桶。"""

    bucket: str
    documents: int


class AnalyticsSummary(BaseModel):
    """分析概览响应。"""

    hours: int
    total_documents: int
    unique_runs: int
    avg_fetch_latency_ms: float
    total_body_length: int
    source_breakdown: list[dict[str, Any]]
    top_tasks: list[dict[str, Any]]


class WorkerStats(BaseModel):
    """worker 运行状态响应。"""

    status: str
    queue: str
    processed_messages: int
    failed_messages: int
    last_run_id: int | None
    last_message_at: datetime | None
    last_error: str | None


class SchedulerState(BaseModel):
    """调度器状态响应。"""

    status: str
    poll_seconds: int
    cycles: int
    last_cycle_at: datetime | None
    last_dispatched_run_ids: list[int]
    active_tasks: int
    next_tasks: list[TaskRead]
