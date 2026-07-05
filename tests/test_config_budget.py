from __future__ import annotations

from pathlib import Path

import pytest

from ai_radar.config import load_run_config, load_sources


def test_run_config_adds_global_budget_and_x_api_defaults(tmp_path: Path):
    path = tmp_path / "run-config.yaml"
    path.write_text("timezone: Asia/Shanghai\n", encoding="utf-8")

    config = load_run_config(path)

    assert config["global_budget"]["max_human_review_items"] == 30
    assert config["global_budget"]["max_today_must_read"] == 10
    assert config["global_budget"]["max_llm_tokens_per_run"] == 200000
    assert config["x_api"]["monthly_budget_usd"] == 20
    assert config["x_api"]["on_budget_exceeded"] == "fallback_browser_x"


def test_sources_get_phase1_defaults(tmp_path: Path):
    path = tmp_path / "sources.yaml"
    path.write_text(
        """
sources:
  - id: demo_blog
    type: company_blog
    enabled: true
    fetch_method: html
    url: https://example.com/news
""",
        encoding="utf-8",
    )

    sources = load_sources(path)

    assert sources[0]["status"] == "active"
    assert sources[0]["dedupe_mode"] == "link"
    assert sources[0]["source_budget"]["daily_fetch_limit"] == 20
    assert sources[0]["source_budget"]["human_review_limit"] == 1


def test_model_and_repo_sources_default_to_stateful(tmp_path: Path):
    path = tmp_path / "sources.yaml"
    path.write_text(
        """
sources:
  - id: demo_model
    type: model_registry
    enabled: true
    fetch_method: huggingface
    url: https://huggingface.co/example
  - id: demo_repo
    type: code_repo
    enabled: true
    fetch_method: github
    url: https://github.com/example/repo
""",
        encoding="utf-8",
    )

    sources = load_sources(path)

    assert [source["dedupe_mode"] for source in sources] == ["stateful", "stateful"]


def test_invalid_source_status_is_rejected(tmp_path: Path):
    path = tmp_path / "sources.yaml"
    path.write_text(
        """
sources:
  - id: bad
    enabled: true
    status: candidate_source
    fetch_method: html
    url: https://example.com
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid status"):
        load_sources(path)
