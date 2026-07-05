from __future__ import annotations

from pathlib import Path

import pytest

from ai_radar.collectors import build_browser_x_url, records_from_x_api_posts, records_from_x_mcp_posts
from ai_radar.config import load_sources
from ai_radar.runner import collect_source


def test_sources_allow_x_api_and_x_mcp_fetch_methods(tmp_path: Path):
    path = tmp_path / "sources.yaml"
    path.write_text(
        """
sources:
  - id: andrewng_x
    enabled: true
    fetch_method: x_api
    url: https://x.com/AndrewYNg
  - id: karpathy_x
    enabled: true
    fetch_method: x_mcp
    url: https://x.com/karpathy
""",
        encoding="utf-8",
    )

    sources = load_sources(path)

    assert [source["fetch_method"] for source in sources] == ["x_api", "x_mcp"]


def test_collect_source_falls_back_to_browser_x_when_x_api_unavailable(monkeypatch):
    calls: list[str] = []
    source = {
        "id": "andrewng_x",
        "type": "person_x",
        "fetch_method": "x_api",
        "url": "https://x.com/AndrewYNg",
        "topics": ["opinion_signal"],
    }

    def fake_api(source_arg, x_config):
        calls.append("api")
        return {"status": "unavailable", "records": [], "error": "missing X API bearer token"}

    def fake_browser(source_arg, x_config):
        calls.append("browser")
        return {"status": "ok", "records": [{"title": "fallback record"}]}

    monkeypatch.setattr("ai_radar.runner.collect_x_api_source", fake_api)
    monkeypatch.setattr("ai_radar.runner.collect_x_source", fake_browser)

    result = collect_source(source, {"x": {}, "x_api": {"enabled": True}})

    assert calls == ["api", "browser"]
    assert result["status"] == "ok"
    assert result["fallback_from"] == "x_api"
    assert result["records"] == [{"title": "fallback record"}]


def test_x_api_source_without_opt_in_falls_back_to_browser_without_api_call(monkeypatch):
    calls: list[str] = []
    source = {
        "id": "andrewng_x",
        "type": "person_x",
        "fetch_method": "x_api",
        "url": "https://x.com/AndrewYNg",
        "topics": ["opinion_signal"],
    }

    def fake_api(source_arg, x_config):
        calls.append("api")
        return {"status": "ok", "records": [{"title": "api record"}]}

    def fake_browser(source_arg, x_config):
        calls.append("browser")
        return {"status": "ok", "records": [{"title": "browser record"}]}

    monkeypatch.setattr("ai_radar.runner.collect_x_api_source", fake_api)
    monkeypatch.setattr("ai_radar.runner.collect_x_source", fake_browser)

    result = collect_source(source, {"x": {}, "x_api": {"enabled": False}})

    assert calls == ["browser"]
    assert result["fallback_from"] == "x_api"
    assert result["fallback_error"] == "x_api_not_enabled"


def test_collect_source_falls_back_from_x_mcp_to_x_api_then_browser(monkeypatch):
    calls: list[str] = []
    source = {"id": "karpathy_x", "type": "person_x", "fetch_method": "x_mcp", "url": "https://x.com/karpathy"}

    def fake_api(source_arg, x_config):
        calls.append("api")
        return {"status": "unavailable", "records": [], "error": "missing bearer token"}

    def fake_browser(source_arg, x_config):
        calls.append("browser")
        return {"status": "ok", "records": [{"title": "browser record"}]}

    monkeypatch.setattr("ai_radar.runner.collect_x_api_source", fake_api)
    monkeypatch.setattr("ai_radar.runner.collect_x_source", fake_browser)

    result = collect_source(source, {"x": {}, "x_api": {"enabled": True}})

    assert calls == ["api", "browser"]
    assert result["status"] == "ok"
    assert result["fallback_from"] == "x_mcp"
    assert result["fallback_error"] == "missing bearer token"


def test_browser_x_url_uses_real_user_posts_route_instead_of_profile_home():
    url = build_browser_x_url({"url": "https://x.com/karpathy"})

    assert url == "https://x.com/search?q=from%3Akarpathy&src=typed_query&f=live"


def test_x_api_records_prefer_note_tweet_full_text_and_real_created_at():
    records = records_from_x_api_posts(
        {
            "data": [
                {
                    "id": "2071988145667928442",
                    "created_at": "2026-06-30T16:04:04.000Z",
                    "text": "short truncated text",
                    "note_tweet": {"text": "full loop engineering text"},
                    "public_metrics": {"like_count": 1},
                }
            ]
        },
        {
            "id": "andrewng_x",
            "type": "person_x",
            "url": "https://x.com/AndrewYNg",
            "topics": ["opinion_signal"],
        },
        "AndrewYNg",
    )

    assert records[0]["url"] == "https://x.com/AndrewYNg/status/2071988145667928442"
    assert records[0]["published_at"] == "2026-06-30T16:04:04+00:00"
    assert records[0]["content_date"] == "2026-07-01"
    assert records[0]["text"] == "full loop engineering text"
    assert records[0]["raw"]["public_metrics"]["like_count"] == 1


def test_x_mcp_records_mark_fetch_method_and_use_note_tweet_text():
    records = records_from_x_mcp_posts(
        {
            "data": [
                {
                    "id": "2071988145667928442",
                    "created_at": "2026-06-30T16:04:04.000Z",
                    "text": "short text",
                    "note_tweet": {"text": "full text from mcp"},
                    "public_metrics": {"like_count": 10},
                }
            ]
        },
        {
            "id": "andrewng_x",
            "type": "person_x",
            "url": "https://x.com/AndrewYNg",
            "topics": ["opinion_signal"],
        },
        "AndrewYNg",
    )

    assert records[0]["url"] == "https://x.com/AndrewYNg/status/2071988145667928442"
    assert records[0]["text"] == "full text from mcp"
    assert records[0]["raw"]["fetch_method"] == "x_mcp"
