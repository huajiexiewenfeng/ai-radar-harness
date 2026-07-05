from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_radar.publish_workflow import workflow_status
from ai_radar.state import load_json_file


def _goal(status: str, detail: str, **extra: Any) -> dict[str, Any]:
    result = {"status": status, "detail": detail}
    result.update(extra)
    return result


def _has_report_section(report: str, section: str) -> bool:
    return f"## {section}" in report


def evaluate_run_health(root: str | Path, run_date: str, require_x: bool = False) -> dict[str, Any]:
    root = Path(root)
    items_path = root / "data" / run_date / "items.json"
    report_path = root / "reports" / f"{run_date}-ai-radar.md"
    draft_path = root / "drafts" / f"{run_date}-topics.md"
    dashboard_html = root / "dashboard" / "index.html"
    dashboard_data = root / "dashboard" / "dashboard-data.js"
    trace_path = root / "harness" / "trace" / f"{run_date}-run.json"

    items = load_json_file(items_path, [])
    trace = load_json_file(trace_path, {})
    report = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    source_errors = trace.get("source_errors", {})
    x_source_errors = {source: message for source, message in source_errors.items() if str(source).endswith("_x")}
    source_warnings = {source: message for source, message in source_errors.items() if not str(source).endswith("_x")}

    goals: dict[str, dict[str, Any]] = {}
    goals["daily_material_library"] = _goal(
        "ok" if items and draft_path.exists() else "missing",
        "items.json and topic draft are present" if items and draft_path.exists() else "missing items.json or topic draft",
        item_count=len(items),
        draft=str(draft_path),
    )
    learning_items = [item for item in items if item.get("learning_score", 0) > 0]
    goals["learning_radar"] = _goal(
        "ok" if learning_items and _has_report_section(report, "前沿知识学习池") else "missing",
        "learning section and scored learning items are present"
        if learning_items and _has_report_section(report, "前沿知识学习池")
        else "missing learning section or learning-scored items",
        item_count=len(learning_items),
        report=str(report_path),
    )
    dynamic_items = [
        item
        for item in items
        if str(item.get("source_type", "")).startswith(("person", "company"))
    ]
    goals["people_company_daily"] = _goal(
        "ok" if dynamic_items and _has_report_section(report, "公司与人物动态") else "missing",
        "people/company section and matching items are present"
        if dynamic_items and _has_report_section(report, "公司与人物动态")
        else "missing people/company section or matching items",
        item_count=len(dynamic_items),
        sources=sorted({item.get("source_id", "unknown") for item in dynamic_items}),
    )
    goals["dashboard"] = _goal(
        "ok" if dashboard_html.exists() and dashboard_data.exists() else "missing",
        "dashboard html and data are present" if dashboard_html.exists() and dashboard_data.exists() else "missing dashboard html or data",
    )
    workflow = workflow_status(root, run_date)
    workflow_goal_status = "ok" if workflow["status"] == "complete" else "missing"
    if workflow["status"] == "waiting_for_human":
        workflow_detail = "selection file is waiting for human decisions"
    elif workflow["status"] == "ready_to_finalize":
        workflow_detail = "selection is decided but articles and memory are not finalized"
    elif workflow["status"] == "complete":
        workflow_detail = "review, selection, articles, and memory pending artifacts are present"
    else:
        workflow_detail = "publish workflow artifacts are missing"
    goals["publish_workflow"] = _goal(
        workflow_goal_status,
        workflow_detail,
        workflow_status=workflow["status"],
        published_count=workflow["published_count"],
        memory_pending_count=workflow["memory_pending_count"],
    )

    x_status = trace.get("x_status", "not_configured")
    if x_status == "ok":
        x = _goal("ok", "X sources collected successfully")
    elif require_x:
        x = _goal("blocked", "X verification required but X sources are unavailable", x_status=x_status, source_errors=x_source_errors)
    else:
        x = _goal("degraded", "X unavailable; public and official sources remain usable", x_status=x_status, source_errors=x_source_errors)

    required_goal_statuses = [goal["status"] for goal in goals.values()]
    if any(status != "ok" for status in required_goal_statuses):
        status = "missing"
    elif x["status"] == "blocked":
        status = "blocked"
    else:
        status = "ok"

    return {
        "date": run_date,
        "status": status,
        "run_status": trace.get("status", "unknown"),
        "goals": goals,
        "workflow": workflow,
        "x": x,
        "source_warnings": source_warnings,
        "trace": str(trace_path),
    }
