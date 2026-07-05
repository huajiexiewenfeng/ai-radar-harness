from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from rapidfuzz import fuzz

from ai_radar.urlutil import canonicalize_url, urlhash


def normalize_title(title: str) -> str:
    lowered = title.lower()
    stripped = re.sub(r"[^\w\s]", " ", lowered, flags=re.UNICODE)
    return re.sub(r"\s+", " ", stripped).strip()


def _recent_dates(run_date: str, days: int) -> set[str]:
    today = date.fromisoformat(run_date)
    return {(today - timedelta(days=offset)).isoformat() for offset in range(days)}


def dedupe_evidence(
    records: list[dict[str, Any]],
    state: dict[str, Any],
    run_date: str,
    title_threshold: int = 90,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    seen_urls: set[str] = set()
    seen_titles: list[str] = [
        entry["norm_title"]
        for entry in state.get("recent_titles", [])
        if entry.get("norm_title") and entry.get("date") != run_date
    ]
    state_keys = state.get("dedupe_keys") or {}
    output: list[dict[str, Any]] = []
    stats = {"url_duplicates": 0, "title_duplicates": 0, "state_duplicates": 0}
    for record in records:
        canonical_url = canonicalize_url(record["url"])
        key = urlhash(canonical_url, 16)
        if key in state_keys and state_keys[key] != run_date:
            stats["state_duplicates"] += 1
            continue
        if canonical_url in seen_urls:
            stats["url_duplicates"] += 1
            continue
        norm_title = normalize_title(record.get("title", ""))
        if norm_title and any(fuzz.token_sort_ratio(norm_title, previous) >= title_threshold for previous in seen_titles):
            stats["title_duplicates"] += 1
            continue
        next_record = dict(record)
        next_record["url"] = canonical_url
        next_record["urlhash16"] = key
        next_record["run_date"] = run_date
        output.append(next_record)
        seen_urls.add(canonical_url)
        if norm_title:
            seen_titles.append(norm_title)
    return output, stats


def update_dedupe_state(
    state: dict[str, Any],
    records: list[dict[str, Any]],
    run_date: str,
    dedupe_window_days: int = 14,
    title_window_days: int = 7,
) -> dict[str, Any]:
    keep_dedupe_dates = _recent_dates(run_date, dedupe_window_days)
    keep_title_dates = _recent_dates(run_date, title_window_days)
    next_state = dict(state)
    dedupe_keys = {
        key: first_seen
        for key, first_seen in (state.get("dedupe_keys") or {}).items()
        if first_seen in keep_dedupe_dates
    }
    titles = [
        entry
        for entry in state.get("recent_titles", [])
        if entry.get("date") in keep_title_dates and entry.get("norm_title")
    ]
    existing_titles = {entry["norm_title"] for entry in titles}
    for record in records:
        key = record.get("urlhash16")
        if key:
            dedupe_keys[key] = run_date
        norm_title = normalize_title(record.get("title", ""))
        if norm_title and norm_title not in existing_titles:
            titles.append({"norm_title": norm_title, "date": run_date})
            existing_titles.add(norm_title)
    next_state["dedupe_keys"] = dedupe_keys
    next_state["recent_titles"] = titles
    return next_state
