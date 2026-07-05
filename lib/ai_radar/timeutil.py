from __future__ import annotations

from datetime import datetime
import re
from typing import Any
from zoneinfo import ZoneInfo


SHANGHAI = ZoneInfo("Asia/Shanghai")
UTC = ZoneInfo("UTC")


def now_shanghai() -> datetime:
    return datetime.now(tz=SHANGHAI)


def run_date_for(moment: datetime | None = None) -> str:
    moment = moment or now_shanghai()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=SHANGHAI)
    return moment.astimezone(SHANGHAI).date().isoformat()


def iso_now() -> str:
    return now_shanghai().isoformat(timespec="seconds")


def parse_iso(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    if normalized.endswith(" UTC"):
        normalized = normalized.removesuffix(" UTC") + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=SHANGHAI)
    return parsed


def content_date_for(published_at: str | None) -> tuple[str | None, str]:
    if not published_at:
        return None, "unknown"
    confidence = "date_only" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", published_at.strip()) else "exact"
    try:
        published = parse_iso(published_at)
    except ValueError:
        return None, "unknown"
    return published.astimezone(SHANGHAI).date().isoformat(), confidence


def normalize_record_dates(record: dict[str, Any]) -> dict[str, Any]:
    next_record = dict(record)
    content_date, confidence = content_date_for(next_record.get("published_at"))
    next_record["content_date"] = content_date
    next_record["date_confidence"] = confidence
    return next_record


def freshness_score(published_at: str | None, captured_at: datetime | None = None) -> int:
    if not published_at:
        return 1
    captured = captured_at or now_shanghai()
    published = parse_iso(published_at)
    hours = (captured.astimezone(UTC) - published.astimezone(UTC)).total_seconds() / 3600
    if hours < 24:
        return 5
    if hours < 48:
        return 4
    if hours < 24 * 7:
        return 3
    if hours < 24 * 14:
        return 2
    return 1
