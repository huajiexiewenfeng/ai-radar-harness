from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_radar.budget import apply_source_candidate_budget
from ai_radar.collectors import collect_http_source, collect_x_api_source, collect_x_source
from ai_radar.config import load_run_config, load_sources
from ai_radar.dedupe import dedupe_evidence, update_dedupe_state
from ai_radar.evidence import merge_source_evidence
from ai_radar.prefilter import load_keywords, prefilter_record
from ai_radar.render import render_daily_report, render_dashboard_data, render_topic_draft
from ai_radar.scoring import score_records
from ai_radar.state import load_json_file, merge_annotations, write_json_file
from ai_radar.timeutil import iso_now, normalize_record_dates, now_shanghai, parse_iso


def filter_recent(records: list[dict[str, Any]], since_hours: int | None) -> list[dict[str, Any]]:
    if not since_hours:
        return records
    kept = []
    for record in records:
        published = record.get("published_at")
        if not published:
            kept.append(record)
            continue
        reference = parse_iso(record["captured_at"]) if record.get("captured_at") else now_shanghai()
        age_hours = (reference - parse_iso(published)).total_seconds() / 3600
        if age_hours <= since_hours:
            kept.append(record)
    return kept


def filter_records_by_content_date(records: list[dict[str, Any]], run_date: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    kept = [record for record in records if record.get("content_date") == run_date]
    unknown = [record for record in records if record.get("date_confidence") == "unknown"]
    other_dated = [
        record
        for record in records
        if record.get("content_date") is not None and record.get("content_date") != run_date
    ]
    return kept, {
        "mode": "content_date",
        "target_date": run_date,
        "input": len(records),
        "kept": len(kept),
        "unknown": len(unknown),
        "other_dated": len(other_dated),
    }


def _recent_runs(root: Path) -> list[dict[str, Any]]:
    trace_dir = root / "harness" / "trace"
    if not trace_dir.exists():
        return []
    runs = []
    for path in sorted(trace_dir.glob("*-run.json"), reverse=True)[:7]:
        data = load_json_file(path, {})
        if data:
            runs.append(
                {
                    "date": data.get("run_date"),
                    "status": data.get("status"),
                    "item_count": data.get("item_count", 0),
                    "failed_sources": len(data.get("failed_sources", [])),
                }
            )
    return runs


def _write_outputs(root: Path, run_date: str, items: list[dict[str, Any]], run: dict[str, Any], state: dict[str, Any]) -> None:
    write_json_file(root / "data" / run_date / "items.json", items)
    write_json_file(root / "harness" / "trace" / f"{run_date}-run.json", run)
    (root / "reports").mkdir(parents=True, exist_ok=True)
    (root / "reports" / f"{run_date}-ai-radar.md").write_text(render_daily_report(run_date, items, run), encoding="utf-8")
    (root / "drafts").mkdir(parents=True, exist_ok=True)
    (root / "drafts" / f"{run_date}-topics.md").write_text(render_topic_draft(run_date, items), encoding="utf-8")
    (root / "dashboard").mkdir(parents=True, exist_ok=True)
    dashboard_data = render_dashboard_data(run_date, items, run, state, _recent_runs(root), root=root)
    (root / "dashboard" / "dashboard-data.js").write_text(dashboard_data, encoding="utf-8")


def _resolve_runtime_paths(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    resolved = dict(config)
    x_config = dict(resolved.get("x", {}))
    profile_dir = x_config.get("profile_dir")
    if profile_dir:
        profile_path = Path(profile_dir)
        if not profile_path.is_absolute():
            profile_path = root / profile_path
        x_config["profile_dir"] = str(profile_path)
    resolved["x"] = x_config
    return resolved


def _source_error_message(result: dict[str, Any]) -> str:
    message = str(result.get("error") or result.get("status") or "unknown error")
    if message == "profile_in_use":
        return "profile_in_use: close the Chrome window using ai-radar/.browser-profile, then rerun"
    if "ProcessSingleton" in message or "profile directory" in message and "already in use" in message:
        return "profile_in_use: close the Chrome window using ai-radar/.browser-profile, then rerun"
    return message.splitlines()[0] if "\n" in message else message


def _sources_by_id(sources: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {source["id"]: source for source in sources}


def _enrich_record_from_source(record: dict[str, Any], source: dict[str, Any], prefilter: dict[str, Any]) -> dict[str, Any]:
    next_record = dict(record)
    next_record["source_id"] = source["id"]
    next_record["source_type"] = source.get("type")
    next_record["source_priority"] = source.get("priority", "low")
    next_record["dedupe_mode"] = source.get("dedupe_mode", "link")
    next_record["prefilter_decision"] = prefilter["decision"]
    next_record["prefilter_reason"] = prefilter["reason"]
    next_record["human_gate_eligible"] = prefilter["human_gate_eligible"]
    return next_record


def apply_phase1_record_controls(
    records: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    keywords: dict[str, list[str]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source_map = _sources_by_id(sources)
    grouped: dict[str, list[dict[str, Any]]] = {}
    stats: dict[str, Any] = {"by_source": {}, "discarded": 0, "archived": 0}
    for record in records:
        source = source_map.get(record.get("source_id"))
        if not source:
            continue
        result = prefilter_record(record, source, keywords)
        if result["decision"] == "discard":
            stats["discarded"] += 1
            continue
        enriched = _enrich_record_from_source(record, source, result)
        if result["decision"] == "archive":
            enriched["status"] = "archive"
            stats["archived"] += 1
        grouped.setdefault(source["id"], []).append(enriched)
    kept: list[dict[str, Any]] = []
    for source_id, source_records in grouped.items():
        source = source_map[source_id]
        source_kept, source_stats = apply_source_candidate_budget(source, source_records)
        source_stats["probation_records"] = sum(1 for record in source_kept if not record.get("human_gate_eligible", True))
        stats["by_source"][source_id] = source_stats
        kept.extend(source_kept)
    return kept, stats


def build_coverage(sources: list[dict[str, Any]], run_date: str, root: Path) -> dict[str, str]:
    coverage: dict[str, str] = {}
    for source in sources:
        evidence_path = root / "evidence" / run_date / f"{source['id']}.json"
        coverage[source["id"]] = "full" if evidence_path.exists() else "none"
    return coverage


def run_from_evidence_snapshot(
    root: str | Path,
    run_date: str,
    evidence: list[dict[str, Any]],
    limit: int,
    since_hours: int | None = None,
    llm_config: dict[str, Any] | None = None,
    dedupe_window_days: int = 14,
    title_window_days: int = 7,
    filter_content_date: bool = False,
) -> dict[str, Any]:
    root = Path(root)
    started_at = iso_now()
    state_path = root / "harness" / "state.json"
    annotations_path = root / "harness" / "annotations.json"
    state = load_json_file(state_path, {"last_run_at": None, "dedupe_keys": {}, "recent_titles": [], "source_health": {}})
    annotations = load_json_file(annotations_path, {"items": {}})
    normalized = [normalize_record_dates(record) for record in evidence]
    recent = normalized if filter_content_date else filter_recent(normalized, since_hours)
    if filter_content_date:
        scoped_records, date_filter = filter_records_by_content_date(recent, run_date)
        dedupe_state = {"dedupe_keys": {}, "recent_titles": []}
    else:
        scoped_records = recent
        date_filter = {
            "mode": "none",
            "target_date": run_date,
            "input": len(recent),
            "kept": len(recent),
            "unknown": len([record for record in recent if record.get("date_confidence") == "unknown"]),
            "other_dated": 0,
        }
        dedupe_state = state
    deduped, dedupe_stats = dedupe_evidence(scoped_records, dedupe_state, run_date)
    items, score_stats = score_records(deduped, run_date, limit=limit, llm_config=llm_config or {"provider": "none"})
    items = merge_annotations(items, annotations)
    llm_degraded = score_stats.get("llm_failures", 0) > 0 and score_stats.get("llm_calls", 0) == 0
    llm_provider = (llm_config or {}).get("provider", "none")
    llm_status = "disabled" if llm_provider == "none" else ("degraded" if llm_degraded else "ok")
    run = {
        "run_date": run_date,
        "status": "degraded" if llm_status == "degraded" else "complete",
        "source_status": "ok",
        "llm_status": llm_status,
        "x_status": "not_configured",
        "started_at": started_at,
        "ended_at": iso_now(),
        "failed_sources": [],
        "dedupe": dedupe_stats,
        "date_filter": date_filter,
        "scoring": score_stats,
        "item_count": len(items),
        "filtered_out": len(normalized) - len(scoped_records),
    }
    if not filter_content_date:
        state = update_dedupe_state(state, deduped, run_date, dedupe_window_days, title_window_days)
        state["last_run_at"] = run["ended_at"]
        write_json_file(state_path, state)
    _write_outputs(root, run_date, items, run, state)
    return run


def collect_source(source: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    fetch_method = source["fetch_method"]
    if fetch_method == "browser_x":
        return collect_x_source(source, config.get("x", {}))
    if fetch_method == "x_api":
        x_api_config = config.get("x_api", {})
        if not x_api_config.get("enabled", False):
            fallback = collect_x_source({**source, "fetch_method": "browser_x"}, config.get("x", {}))
            fallback["fallback_from"] = "x_api"
            fallback["fallback_error"] = "x_api_not_enabled"
            fallback["x_api_status"] = "not_enabled"
            return fallback
        result = collect_x_api_source(source, {**config.get("x", {}), **x_api_config})
        if result.get("status") == "ok" and result.get("records"):
            return result
        fallback = collect_x_source({**source, "fetch_method": "browser_x"}, config.get("x", {}))
        fallback["fallback_from"] = "x_api"
        fallback["fallback_error"] = result.get("error")
        return fallback
    if fetch_method == "x_mcp":
        x_api_config = config.get("x_api", {})
        if x_api_config.get("enabled", False):
            result = collect_x_api_source({**source, "fetch_method": "x_api"}, {**config.get("x", {}), **x_api_config})
        else:
            result = {"status": "unavailable", "records": [], "error": "x_mcp is not injected into local Python runner"}
        if result.get("status") == "ok" and result.get("records"):
            result["fallback_from"] = "x_mcp"
            return result
        fallback = collect_x_source({**source, "fetch_method": "browser_x"}, config.get("x", {}))
        fallback["fallback_from"] = "x_mcp"
        fallback["fallback_error"] = result.get("error")
        return fallback
    return collect_http_source(source)


def run_live(root: str | Path, run_date: str, since_hours: int | None, limit: int, filter_by_content_date: bool = False) -> dict[str, Any]:
    root = Path(root)
    config = _resolve_runtime_paths(root, load_run_config(root / "harness" / "run-config.yaml"))
    sources = load_sources(root / "sources" / "sources.yaml")
    all_records: list[dict[str, Any]] = []
    failed_sources: list[str] = []
    source_errors: dict[str, str] = {}
    x_statuses: list[str] = []
    for source in sources:
        try:
            result = collect_source(source, config)
        except Exception as exc:
            result = {"status": "failed", "records": [], "error": str(exc)}
        records = result.get("records", [])
        if result.get("status") != "ok":
            failed_sources.append(source["id"])
            source_errors[source["id"]] = _source_error_message(result)
        if source["fetch_method"] in {"browser_x", "x_api", "x_mcp"}:
            x_statuses.append(result.get("status", "failed"))
        evidence_path = root / "evidence" / run_date / f"{source['id']}.json"
        merge_source_evidence(evidence_path, source["id"], records)
        all_records.extend(records)
    keywords = load_keywords(root / "sources" / "keywords.yaml")
    controlled_records, phase1_stats = apply_phase1_record_controls(all_records, sources, keywords)
    llm_config = dict(config.get("llm") or {})
    llm_config["max_llm_tokens_per_run"] = config.get("global_budget", {}).get("max_llm_tokens_per_run", 200000)
    run = run_from_evidence_snapshot(
        root,
        run_date,
        controlled_records,
        limit,
        since_hours=since_hours,
        llm_config=llm_config,
        dedupe_window_days=config.get("dedupe_window_days", 14),
        title_window_days=config.get("title_window_days", 7),
        filter_content_date=filter_by_content_date,
    )
    run["budget"] = {
        "phase1": phase1_stats,
        "global": config.get("global_budget", {}),
    }
    run["coverage"] = build_coverage(sources, run_date, root)
    run["source_status"] = "partial" if failed_sources else "ok"
    if not x_statuses:
        run["x_status"] = "not_configured"
    elif all(status == "ok" for status in x_statuses):
        run["x_status"] = "ok"
    elif any(status == "session_expired" for status in x_statuses):
        run["x_status"] = "session_expired"
    else:
        run["x_status"] = "unavailable"
    if failed_sources and run.get("llm_status") == "degraded":
        run["status"] = "partial_degraded"
    elif failed_sources:
        run["status"] = "partial"
    run["failed_sources"] = failed_sources
    run["source_errors"] = source_errors
    state = load_json_file(root / "harness" / "state.json", {})
    items = load_json_file(root / "data" / run_date / "items.json", [])
    _write_outputs(root, run_date, items, run, state)
    return run
