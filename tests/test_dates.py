from __future__ import annotations

from ai_radar.timeutil import normalize_record_dates


def test_normalize_record_dates_uses_shanghai_content_date():
    record = normalize_record_dates(
        {
            "published_at": "2026-07-03T20:30:00+00:00",
            "captured_at": "2026-07-05T08:00:00+08:00",
        }
    )

    assert record["content_date"] == "2026-07-04"
    assert record["date_confidence"] == "exact"


def test_normalize_record_dates_marks_unknown_when_publish_time_missing():
    record = normalize_record_dates({"published_at": None, "captured_at": "2026-07-05T08:00:00+08:00"})

    assert record["content_date"] is None
    assert record["date_confidence"] == "unknown"
