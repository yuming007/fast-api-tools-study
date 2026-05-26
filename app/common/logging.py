from __future__ import annotations

import logging

from app.common.config import get_settings


def configure_logging(service_name: str) -> logging.Logger:
    """统一初始化日志格式，让所有服务输出风格一致。"""

    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        force=True,
    )
    return logging.getLogger(service_name)
