from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """返回不带时区信息的 UTC 时间，便于统一写入数据库。"""

    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_iso_datetime(value: str | None) -> datetime | None:
    """把 ISO 时间字符串解析为 UTC naive datetime。"""

    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed
