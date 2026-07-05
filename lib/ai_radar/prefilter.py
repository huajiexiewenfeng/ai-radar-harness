from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_keywords(path: str | Path) -> dict[str, list[str]]:
    target = Path(path)
    if not target.exists():
        return {"include": [], "exclude": []}
    data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    return {
        "include": [str(value).lower() for value in data.get("include", [])],
        "exclude": [str(value).lower() for value in data.get("exclude", [])],
    }


def _combined_text(record: dict[str, Any]) -> str:
    return " ".join([str(record.get("title") or ""), str(record.get("text") or "")]).lower()


def _hits_any(text: str, keywords: list[str]) -> bool:
    return any(keyword and keyword in text for keyword in keywords)


def _is_share_or_reply(record: dict[str, Any]) -> bool:
    raw = record.get("raw") or {}
    return bool(raw.get("is_retweet") or raw.get("is_reply") or raw.get("referenced_tweets"))


def prefilter_record(record: dict[str, Any], source: dict[str, Any], keywords: dict[str, list[str]]) -> dict[str, Any]:
    text = _combined_text(record)
    noise_level = (source.get("source_budget") or {}).get("noise_level", "low")
    if _hits_any(text, keywords.get("exclude", [])):
        return {"decision": "archive", "reason": "exclude_keyword", "human_gate_eligible": False}
    if noise_level in {"medium", "high"} and not _hits_any(text, keywords.get("include", [])):
        return {"decision": "discard", "reason": "missing_include_keyword", "human_gate_eligible": False}
    if noise_level == "high" and _is_share_or_reply(record):
        return {"decision": "discard", "reason": "high_noise_share_or_reply", "human_gate_eligible": False}
    source_status = source.get("status", "active")
    return {
        "decision": "candidate",
        "reason": "probation" if source_status == "probation" else "matched",
        "human_gate_eligible": source_status == "active",
    }
