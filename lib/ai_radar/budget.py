from __future__ import annotations

from typing import Any


PRIORITY_RANK = {"high": 4, "medium": 3, "low": 2}


def source_tier(source_or_item: dict[str, Any]) -> int:
    return PRIORITY_RANK.get(str(source_or_item.get("priority") or source_or_item.get("source_priority") or "low"), 1)


def effective_candidate_limit(source: dict[str, Any]) -> int:
    budget = source.get("source_budget") or {}
    limit = int(budget.get("daily_candidate_limit", 5) or 5)
    if budget.get("noise_level") == "high":
        return max(1, limit // 2)
    return max(0, limit)


def apply_source_candidate_budget(source: dict[str, Any], records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    candidates = [record for record in records if record.get("prefilter_decision", "candidate") == "candidate"]
    limit = effective_candidate_limit(source)
    kept = candidates[:limit]
    return kept, {"source_candidate_evicted": max(0, len(candidates) - len(kept))}


def _human_sort_key(item: dict[str, Any]) -> tuple[int, float, str]:
    return (
        source_tier(item),
        float(item.get("daily_rank", 0) or 0),
        str(item.get("published_at") or ""),
    )


def apply_global_human_budget(items: list[dict[str, Any]], global_budget: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    eligible = [item for item in items if item.get("status") == "candidate" and item.get("human_gate_eligible", True)]
    ordered = sorted(eligible, key=_human_sort_key, reverse=True)
    limit = int(global_budget.get("max_human_review_items", 30) or 30)
    kept = ordered[:limit]
    evicted = ordered[limit:]
    for item in evicted:
        item["status"] = "archive"
        item["archive_reason"] = "budget_evicted"
    return kept, {"budget_evicted": {"count": len(evicted), "items": [item["id"] for item in evicted]}}
