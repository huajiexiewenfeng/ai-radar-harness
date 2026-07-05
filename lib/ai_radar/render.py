from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_radar.publish_workflow import workflow_status
from ai_radar.state import load_json_file


def _top_items(items: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: item.get("daily_rank", 0), reverse=True)[:limit]


def _dynamic_items(items: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    priority_prefixes = ("person", "company")
    preferred = [
        item
        for item in items
        if str(item.get("source_type", "")).startswith(priority_prefixes)
    ]
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in preferred + items:
        item_id = item.get("id") or item.get("url")
        if item_id in seen:
            continue
        selected.append(item)
        seen.add(item_id)
        if len(selected) >= limit:
            break
    return selected


def _date_lines(item: dict[str, Any]) -> list[str]:
    content_date = item.get("content_date") or "未知"
    published_at = item.get("published_at") or "未知"
    captured_at = item.get("captured_at") or "未知"
    confidence = item.get("date_confidence") or "unknown"
    return [
        f"- 内容日期：{content_date}（可信度：`{confidence}`）",
        f"- 发布时间：{published_at}",
        f"- 采集时间：{captured_at}",
    ]


def render_daily_report(run_date: str, items: list[dict[str, Any]], run: dict[str, Any]) -> str:
    lines = [f"# AI Radar Daily - {run_date}", ""]
    lines += ["## 今日最值得关注", ""]
    for index, item in enumerate(_top_items(items), start=1):
        lines += [
            f"### {index}. {item['title']}",
            "",
            f"- 来源：[{item.get('source_id', 'unknown')}]({item['url']})",
            f"- 类型：`{item.get('content_type', 'unknown')}`",
            *_date_lines(item),
            f"- 一句话摘要：{item.get('summary', 'pending')}",
            f"- 为什么重要：{item.get('why_it_matters', 'pending')}",
            f"- 发布价值：{item.get('publish_score')}",
            f"- 学习价值：{item.get('learning_score')}",
            "",
        ]
    lines += ["## 公众号选题池", ""]
    promoted = [item for item in items if item.get("status") in {"promote", "candidate"}]
    for item in promoted[:5]:
        for angle in item.get("article_angles", [])[:2]:
            lines += [f"- {angle}（来源：[{item['title']}]({item['url']})）"]
    lines += ["", "## 前沿知识学习池", ""]
    for item in sorted(items, key=lambda value: value.get("learning_rank", 0), reverse=True)[:5]:
        notes = "；".join(item.get("learning_notes", [])) or item["title"]
        lines += [f"- **{item['title']}**：{notes}"]
    lines += ["", "## 公司与人物动态", ""]
    for item in _dynamic_items(items):
        content_date = item.get("content_date") or "日期未知"
        lines += [f"- `{item.get('source_id', 'unknown')}`：[{item['title']}]({item['url']})（内容日期：{content_date}）"]
    lines += ["", "## 可忽略但留档", ""]
    ignored = [item for item in items if item.get("status") in {"archive", "ignore", "unscored"}]
    lines += [f"- [{item['title']}]({item['url']})" for item in ignored] or ["- 今日无。"]
    lines += ["", "## 本次运行状态", ""]
    lines += [
        f"- 状态：`{run.get('status', 'unknown')}`",
        f"- 来源状态：`{run.get('source_status', 'unknown')}`",
        f"- LLM 状态：`{run.get('llm_status', 'unknown')}`",
        f"- X 状态：`{run.get('x_status', 'not_configured')}`",
        f"- 失败来源：{len(run.get('failed_sources', []))}",
        f"- 新增素材：{len(items)}",
    ]
    source_errors = run.get("source_errors") or {}
    if source_errors:
        lines += ["", "失败详情："]
        for source_id, message in source_errors.items():
            lines += [f"- `{source_id}`：{message}"]
    coverage = run.get("coverage") or {}
    lines += ["", "## 来源覆盖", ""]
    if coverage:
        for source_id, value in sorted(coverage.items()):
            lines += [f"- `{source_id}`：{value}"]
    else:
        lines += ["- 暂无 coverage 数据。"]
    budget = run.get("budget") or {}
    global_budget = budget.get("global") or {}
    phase1_budget = budget.get("phase1") or {}
    lines += ["", "## 预算消耗", ""]
    lines += [
        f"- Human Gate 上限：{global_budget.get('max_human_review_items', '未知')}",
        f"- 今日必看上限：{global_budget.get('max_today_must_read', '未知')}",
        f"- 预筛丢弃：{phase1_budget.get('discarded', 0)}",
        f"- 预筛归档：{phase1_budget.get('archived', 0)}",
    ]
    return "\n".join(lines) + "\n"


def render_topic_draft(run_date: str, items: list[dict[str, Any]]) -> str:
    def _section(title: str, section_items: list[dict[str, Any]]) -> list[str]:
        lines = [f"## {title}", ""]
        if not section_items:
            lines += ["- 暂无。", ""]
            return lines
        for item in section_items:
            lines += [f"### {item['title']}", ""]
            for angle in item.get("article_angles", []):
                lines += [f"- {angle}"]
            lines += [f"- 来源：{item['url']}", ""]
        return lines

    promoted = [item for item in items if item.get("status") == "promote"]
    candidates = sorted(
        (item for item in items if item.get("status") == "candidate"),
        key=lambda item: item.get("daily_rank", 0),
        reverse=True,
    )[:5]
    lines = [f"# AI Radar 选题池 - {run_date}", ""]
    lines += _section("已确认选题", promoted)
    lines += _section("候选选题", candidates)
    return "\n".join(lines)


def render_dashboard_data(
    run_date: str,
    items: list[dict[str, Any]],
    run: dict[str, Any],
    state: dict[str, Any],
    recent_runs: list[dict[str, Any]],
    root: str | Path | None = None,
) -> str:
    payload = {"date": run_date, "run": run, "items": items, "state": state, "recent_runs": recent_runs}
    if root is not None:
        root_path = Path(root)
        payload["workflow"] = workflow_status(root_path, run_date)
        payload["human_selection"] = _human_selection_payload(root_path, run_date)
        payload["decision_summary"] = _decision_summary(payload["human_selection"]["items"])
    return "window.aiRadarData = " + json.dumps(payload, ensure_ascii=False, indent=2) + ";\n"


def _human_selection_payload(root: Path, run_date: str) -> dict[str, Any]:
    review = load_json_file(root / "review" / f"{run_date}-review.json", {})
    selection = load_json_file(root / "review" / f"{run_date}-selection.json", {})
    review_by_id = {entry.get("item_id"): entry for entry in review.get("items", [])}
    items = []
    for entry in selection.get("items", []):
        review_entry = review_by_id.get(entry.get("item_id"), {})
        item = dict(review_entry)
        item.update(entry)
        item["decision_patch"] = {
            "item_id": entry.get("item_id"),
            "decision": entry.get("suggested_decision", "publish"),
            "note": entry.get("note", ""),
        }
        items.append(item)
    return {
        "selection_path": str(root / "review" / f"{run_date}-selection.json"),
        "review_path": str(root / "review" / f"{run_date}-review.md"),
        "items": items,
    }


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _decision_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    suggested = _count_by(items, "suggested_decision")
    decisions = _count_by(items, "decision")
    return {
        "total": len(items),
        "suggested": {
            "publish": suggested.get("publish", 0),
            "wiki_only": suggested.get("wiki_only", 0),
            "ignore": suggested.get("ignore", 0),
            "pending": suggested.get("pending", 0),
        },
        "decisions": {
            "publish": decisions.get("publish", 0),
            "wiki_only": decisions.get("wiki_only", 0),
            "ignore": decisions.get("ignore", 0),
            "pending": decisions.get("pending", 0),
        },
        "unknown_date": sum(1 for item in items if not item.get("content_date")),
        "by_source": _count_by(items, "source_id"),
        "by_content_date": _count_by(items, "content_date"),
    }
