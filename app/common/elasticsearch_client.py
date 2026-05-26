from __future__ import annotations

import logging
import time
from typing import Any

from elasticsearch import Elasticsearch, helpers

from app.common.config import get_settings

logger = logging.getLogger("elasticsearch")
_client = None


def get_elasticsearch_client() -> Elasticsearch:
    """创建并缓存 Elasticsearch 客户端。"""

    global _client
    if _client is None:
        settings = get_settings()
        _client = Elasticsearch(settings.elasticsearch_url)
    return _client


def wait_for_elasticsearch(max_attempts: int = 60, delay_seconds: float = 2.0) -> None:
    """在启动阶段等待 Elasticsearch 可访问。"""

    client = get_elasticsearch_client()
    for attempt in range(1, max_attempts + 1):
        try:
            client.info()
            return
        except Exception:
            if attempt == max_attempts:
                raise
            time.sleep(delay_seconds)


def ensure_articles_index() -> None:
    """确保全文检索索引存在。"""

    settings = get_settings()
    client = get_elasticsearch_client()
    if client.indices.exists(index=settings.elasticsearch_index):
        return

    client.indices.create(
        index=settings.elasticsearch_index,
        settings={
            "number_of_shards": 1,
            "number_of_replicas": 0,
        },
        mappings={
            "properties": {
                "external_id": {"type": "keyword"},
                "task_id": {"type": "integer"},
                "run_id": {"type": "integer"},
                "topic": {"type": "keyword"},
                "source": {"type": "keyword"},
                "author": {"type": "keyword"},
                "title": {"type": "text"},
                "summary": {"type": "text"},
                "content": {"type": "text"},
                "published_at": {"type": "date"},
            }
        },
    )


def bulk_index_articles(documents: list[dict[str, Any]]) -> int:
    """批量写入文章正文索引，提升导入效率。"""

    if not documents:
        return 0

    settings = get_settings()
    client = get_elasticsearch_client()
    actions = [
        {
            "_index": settings.elasticsearch_index,
            "_id": document["external_id"],
            "_source": document,
        }
        for document in documents
    ]
    successes, errors = helpers.bulk(
        client,
        actions,
        refresh=True,
        raise_on_error=False,
    )
    if errors:
        logger.warning("Elasticsearch bulk indexing finished with %s errors", len(errors))
    return int(successes)
