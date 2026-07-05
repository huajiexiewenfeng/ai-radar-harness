from __future__ import annotations

from pathlib import Path

from ai_radar.config import load_run_config, load_sources


ROOT = Path(__file__).resolve().parents[1]
SOURCES_YAML = ROOT / "sources" / "sources.yaml"
RUN_CONFIG = ROOT / "harness" / "run-config.yaml"


def test_real_sources_yaml_loads_with_phase1_fields():
    sources = load_sources(SOURCES_YAML)

    assert sources
    assert all(source["status"] in {"active", "probation"} for source in sources)
    assert all(source["dedupe_mode"] in {"link", "stateful"} for source in sources)
    assert all("source_budget" in source for source in sources)


def test_x_sources_use_x_mcp_as_first_route():
    config = load_run_config(RUN_CONFIG)
    sources = load_sources(SOURCES_YAML)
    x_sources = [source for source in sources if source["type"] in {"person_x", "company_x"}]

    assert x_sources
    assert config["x_mcp"]["enabled"] is True
    assert config["x_api"]["enabled"] is True
    assert all(source["fetch_method"] == "x_mcp" for source in x_sources)


def test_x_sources_have_stable_username_and_user_id():
    sources = load_sources(SOURCES_YAML)
    x_sources = [source for source in sources if source["type"] in {"person_x", "company_x"}]

    assert all(source.get("username") for source in x_sources)
    assert all(source.get("user_id") for source in x_sources)


def test_real_run_config_has_global_budget():
    config = load_run_config(RUN_CONFIG)

    assert config["global_budget"]["max_human_review_items"] == 30
    assert config["global_budget"]["max_llm_tokens_per_run"] == 200000
