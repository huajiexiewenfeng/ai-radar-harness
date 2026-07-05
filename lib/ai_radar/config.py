from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


DEFAULT_SOURCE_BUDGET: dict[str, Any] = {
    "daily_fetch_limit": 20,
    "daily_candidate_limit": 5,
    "llm_candidate_limit": 2,
    "human_review_limit": 1,
    "max_text_chars": 4000,
    "min_publish_score": 3,
    "min_learning_score": 3,
    "noise_level": "low",
}

DEFAULT_RUN_CONFIG: dict[str, Any] = {
    "timezone": "Asia/Shanghai",
    "since_hours": 48,
    "limit": 30,
    "dedupe_window_days": 14,
    "title_window_days": 7,
    "global_budget": {
        "max_sources_per_run": 80,
        "max_records_per_run": 500,
        "max_llm_items_per_run": 30,
        "max_llm_tokens_per_run": 200000,
        "max_human_review_items": 30,
        "max_today_must_read": 10,
        "max_publish_candidates": 20,
        "max_learning_candidates": 20,
    },
    "llm": {
        "provider": "none",
        "model": "claude-sonnet-5",
        "api_key_env": "AI_RADAR_LLM_KEY",
        "max_input_chars": 4000,
    },
    "x": {
        "profile_dir": "../.browser-profile",
        "max_items_per_account": 20,
        "stage_timeout_minutes": 5,
        "api_bearer_token_env": "X_API_BEARER_TOKEN",
    },
    "x_api": {
        "enabled": False,
        "api_key_env": "AI_RADAR_X_API_KEY",
        "monthly_budget_usd": 20,
        "on_budget_exceeded": "fallback_browser_x",
    },
}

VALID_FETCH_METHODS = {"rss", "html", "browser_x", "x_api", "x_mcp", "huggingface", "github", "modelscope"}
VALID_SOURCE_STATUS = {"active", "probation"}
VALID_DEDUPE_MODES = {"link", "stateful"}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_yaml(path: str | Path) -> dict[str, Any]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def load_run_config(path: str | Path) -> dict[str, Any]:
    return _deep_merge(DEFAULT_RUN_CONFIG, load_yaml(path))


def _default_dedupe_mode(source: dict[str, Any]) -> str:
    if source.get("type") in {"model_registry", "code_repo"}:
        return "stateful"
    return "link"


def _enrich_source(source: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(source)
    enriched["status"] = enriched.get("status", "active")
    enriched["dedupe_mode"] = enriched.get("dedupe_mode", _default_dedupe_mode(enriched))
    enriched["source_budget"] = _deep_merge(DEFAULT_SOURCE_BUDGET, enriched.get("source_budget") or {})
    return enriched


def load_sources(path: str | Path) -> list[dict[str, Any]]:
    data = load_yaml(path)
    raw_sources = data.get("sources", [])
    if not isinstance(raw_sources, list):
        raise ValueError("sources.yaml must contain a sources list")
    enabled = []
    for source in raw_sources:
        if not source.get("enabled", True):
            continue
        source = _enrich_source(source)
        source_id = source.get("id")
        fetch_method = source.get("fetch_method")
        if not source_id:
            raise ValueError("source missing id")
        if fetch_method not in VALID_FETCH_METHODS:
            raise ValueError(f"{source_id} has invalid fetch_method {fetch_method!r}")
        if source["status"] not in VALID_SOURCE_STATUS:
            raise ValueError(f"{source_id} has invalid status {source['status']!r}")
        if source["dedupe_mode"] not in VALID_DEDUPE_MODES:
            raise ValueError(f"{source_id} has invalid dedupe_mode {source['dedupe_mode']!r}")
        if fetch_method == "rss" and not source.get("feed_url"):
            raise ValueError(f"{source_id} fetch_method=rss requires feed_url")
        enabled.append(source)
    return enabled
