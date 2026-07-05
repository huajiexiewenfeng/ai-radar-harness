from __future__ import annotations

from pathlib import Path

from ai_radar.runner import run_from_evidence_snapshot
from ai_radar.urlutil import urlhash


def _record(title: str, url: str, published_at: str | None) -> dict[str, object]:
    return {
        "source_id": "test",
        "source_type": "company_official",
        "title": title,
        "url": url,
        "author": None,
        "published_at": published_at,
        "captured_at": "2026-07-05T08:00:00+08:00",
        "text": title,
        "raw": {},
        "topics": [],
    }


def test_explicit_date_mode_keeps_only_matching_content_date(tmp_path: Path):
    run = run_from_evidence_snapshot(
        tmp_path,
        "2026-07-04",
        [
            _record("July fourth item", "https://example.com/july-4", "2026-07-04T02:00:00+00:00"),
            _record("July fifth item", "https://example.com/july-5", "2026-07-05T02:00:00+00:00"),
            _record("Unknown date item", "https://example.com/unknown", None),
        ],
        limit=10,
        since_hours=None,
        llm_config={"provider": "none"},
        filter_content_date=True,
    )

    items = __import__("json").loads((tmp_path / "data" / "2026-07-04" / "items.json").read_text(encoding="utf-8"))
    assert run["date_filter"]["mode"] == "content_date"
    assert run["date_filter"]["kept"] == 1
    assert run["date_filter"]["unknown"] == 1
    assert [item["title"] for item in items] == ["July fourth item"]
    assert items[0]["content_date"] == "2026-07-04"


def test_default_mode_does_not_drop_unknown_date_items(tmp_path: Path):
    run_from_evidence_snapshot(
        tmp_path,
        "2026-07-05",
        [_record("Unknown date item", "https://example.com/unknown", None)],
        limit=10,
        since_hours=None,
        llm_config={"provider": "none"},
        filter_content_date=False,
    )

    items = __import__("json").loads((tmp_path / "data" / "2026-07-05" / "items.json").read_text(encoding="utf-8"))
    assert [item["title"] for item in items] == ["Unknown date item"]
    assert items[0]["date_confidence"] == "unknown"


def test_explicit_date_mode_ignores_cross_day_state_dedupe(tmp_path: Path):
    state_path = tmp_path / "harness" / "state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        __import__("json").dumps(
            {
                "last_run_at": "2026-07-05T08:00:00+08:00",
                "dedupe_keys": {urlhash("https://example.com/july-4", 16): "2026-07-05"},
                "recent_titles": [],
                "source_health": {},
            }
        ),
        encoding="utf-8",
    )

    run = run_from_evidence_snapshot(
        tmp_path,
        "2026-07-04",
        [_record("July fourth item", "https://example.com/july-4", "2026-07-04T02:00:00+00:00")],
        limit=10,
        since_hours=None,
        llm_config={"provider": "none"},
        filter_content_date=True,
    )

    items = __import__("json").loads((tmp_path / "data" / "2026-07-04" / "items.json").read_text(encoding="utf-8"))
    assert run["dedupe"]["state_duplicates"] == 0
    assert [item["title"] for item in items] == ["July fourth item"]
