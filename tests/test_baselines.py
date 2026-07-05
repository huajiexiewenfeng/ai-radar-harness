from __future__ import annotations

from pathlib import Path

from ai_radar.baselines import baseline_path, load_baseline, stateful_versioned_url, update_baseline_entry


def test_load_baseline_returns_schema_when_missing(tmp_path: Path):
    baseline = load_baseline(tmp_path, "deepseek_huggingface")

    assert baseline["schema_version"] == 1
    assert baseline["source_id"] == "deepseek_huggingface"
    assert baseline["entries"] == {}


def test_update_baseline_entry_writes_source_file(tmp_path: Path):
    baseline = load_baseline(tmp_path, "deepseek_huggingface")
    update_baseline_entry(
        tmp_path,
        baseline,
        "https://huggingface.co/deepseek-ai/DeepSeek-V4",
        {
            "etag": None,
            "last_modified": "2026-07-01T08:00:00+00:00",
            "version": "V4",
            "content_hash": "a3f9c2d1e0b47788",
            "last_checked": "2026-07-05T09:00:00+08:00",
        },
    )

    saved = load_baseline(tmp_path, "deepseek_huggingface")

    assert baseline_path(tmp_path, "deepseek_huggingface").exists()
    assert saved["entries"]["https://huggingface.co/deepseek-ai/DeepSeek-V4"]["version"] == "V4"


def test_stateful_versioned_url_uses_version_or_hash():
    assert (
        stateful_versioned_url("https://example.com/model", {"version": "V4", "content_hash": "abcdef123456"})
        == "https://example.com/model#v=V4"
    )
    assert (
        stateful_versioned_url("https://example.com/model", {"content_hash": "abcdef123456"})
        == "https://example.com/model#v=abcdef12"
    )
