from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_radar.budget import apply_global_human_budget
from ai_radar.config import DEFAULT_RUN_CONFIG, load_run_config
from ai_radar.dedupe import normalize_title
from ai_radar.scoring import score_records
from ai_radar.state import load_json_file, write_json_file
from ai_radar.urlutil import canonicalize_url


DECISIONS = {"publish", "wiki_only", "ignore"}
GENERIC_DECISION_TITLES = {
    "blog",
    "home",
    "news",
    "post",
    "posts",
    "research",
    "forum",
    "thread",
    "update",
    "updates",
}


def _score(item: dict[str, Any], key: str) -> int:
    try:
        return int(item.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0


def _suggest_decision(item: dict[str, Any]) -> str:
    if item.get("recommended_action") in DECISIONS:
        return item["recommended_action"]
    if item.get("status") in {"archive", "ignore", "unscored"}:
        return "ignore"
    publish_score = _score(item, "publish_score")
    learning_score = _score(item, "learning_score")
    importance = _score(item, "importance")
    if publish_score >= 4 and importance >= 3:
        return "publish"
    if learning_score >= 4 or importance >= 4:
        return "wiki_only"
    return "ignore"


def _recommendation_reason(item: dict[str, Any], decision: str) -> str:
    title = item.get("title", "这条内容")
    if decision == "publish":
        return f"{title} 同时具备发布价值和学习价值，适合作为今日文章主素材。"
    if decision == "wiki_only":
        return f"{title} 暂时不一定适合今天发文，但适合沉淀为后续文章的背景资料。"
    return f"{title} 当前价值较低或重复度较高，建议忽略。"


def _review_entry(item: dict[str, Any]) -> dict[str, Any]:
    decision = _suggest_decision(item)
    return {
        "item_id": item["id"],
        "title": item.get("title", "Untitled"),
        "url": item.get("url"),
        "source_id": item.get("source_id"),
        "source_type": item.get("source_type"),
        "content_type": item.get("content_type"),
        "topics": item.get("topics", []),
        "content_date": item.get("content_date"),
        "published_at": item.get("published_at"),
        "suggested_decision": decision,
        "reason": _recommendation_reason(item, decision),
        "summary": item.get("summary", ""),
        "why_it_matters": item.get("why_it_matters", ""),
        "article_angles": item.get("article_angles", []),
        "scores": {
            "importance": _score(item, "importance"),
            "publish": _score(item, "publish_score"),
            "learning": _score(item, "learning_score"),
        },
    }


def build_review(run_date: str, items: list[dict[str, Any]], global_budget: dict[str, Any] | None = None) -> dict[str, Any]:
    reviewable = [
        item
        for item in items
        if item.get("status", "candidate") == "candidate" and item.get("human_gate_eligible", True)
    ]
    reviewable, budget_stats = apply_global_human_budget(reviewable, global_budget or {"max_human_review_items": 30})
    entries = [_review_entry(item) for item in reviewable]
    return {
        "date": run_date,
        "status": "review_ready",
        "summary": {
            "total_items": len(entries),
            "decision_pool": "items",
            "publish_candidates": sum(1 for entry in entries if entry["suggested_decision"] == "publish"),
            "wiki_candidates": sum(1 for entry in entries if entry["suggested_decision"] == "wiki_only"),
            "ignore_candidates": sum(1 for entry in entries if entry["suggested_decision"] == "ignore"),
            "budget_evicted": budget_stats["budget_evicted"],
        },
        "items": entries,
    }


def _load_evidence_records(root: Path, run_date: str) -> list[dict[str, Any]]:
    evidence_dir = root / "evidence" / run_date
    if not evidence_dir.exists():
        return []
    records: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for path in sorted(evidence_dir.glob("*.json")):
        data = load_json_file(path, {})
        for record in data.get("records", []):
            if record.get("content_date") != run_date:
                continue
            url = record.get("url")
            if not url or url in seen_urls:
                continue
            records.append(record)
            seen_urls.add(url)
    return records


def _decision_record_quality(record: dict[str, Any]) -> int:
    text = str(record.get("text") or "")
    title = str(record.get("title") or "")
    published_bonus = 20 if record.get("published_at") or record.get("content_date") else 0
    return len(text.strip()) + min(len(title.strip()), 80) + published_bonus


def _decision_dedupe_key(record: dict[str, Any]) -> str:
    url = str(record.get("url") or "")
    canonical_url = canonicalize_url(url) if url else ""
    norm_title = normalize_title(str(record.get("title") or ""))
    if not norm_title or norm_title in GENERIC_DECISION_TITLES:
        return f"url:{canonical_url}"
    source = record.get("source_id") or record.get("source_type") or "unknown_source"
    return f"source-title:{source}:{norm_title}"


def _dedupe_decision_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for record in records:
        key = _decision_dedupe_key(record)
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = record
            order.append(key)
            continue
        if _decision_record_quality(record) > _decision_record_quality(existing):
            by_key[key] = record
    return [by_key[key] for key in order]


def load_decision_pool(root: str | Path, run_date: str, limit: int = 200) -> tuple[list[dict[str, Any]], str]:
    root = Path(root)
    evidence_records = _dedupe_decision_records(_load_evidence_records(root, run_date))
    if evidence_records:
        items, _stats = score_records(evidence_records, run_date, limit=limit, llm_config={"provider": "none"})
        return items, "evidence"
    return load_json_file(root / "data" / run_date / "items.json", []), "items"


def render_review_markdown(review: dict[str, Any]) -> str:
    lines = [f"# AI Radar 人工确认清单 - {review['date']}", ""]
    summary = review.get("summary", {})
    lines += [
        f"- 候选总数：{summary.get('total_items', 0)}",
        f"- 建议发文：{summary.get('publish_candidates', 0)}",
        f"- 建议沉淀：{summary.get('wiki_candidates', 0)}",
        f"- 建议忽略：{summary.get('ignore_candidates', 0)}",
        "",
        "## 待确认内容",
        "",
    ]
    for entry in review.get("items", []):
        lines += [
            f"### {entry['title']}",
            "",
            f"- 建议：`{entry['suggested_decision']}`",
            f"- 来源：[{entry.get('source_id', 'unknown')}]({entry.get('url')})",
            f"- 内容日期：{entry.get('content_date') or '未知'}",
            f"- 理由：{entry.get('reason', '')}",
            f"- 摘要：{entry.get('summary', '')}",
            "",
        ]
    return "\n".join(lines).strip() + "\n"


def initialize_selection(root: str | Path, run_date: str, review: dict[str, Any]) -> dict[str, Any]:
    selection = {
        "date": run_date,
        "status": "pending_human_review",
        "instructions": "把每条 decision 从 pending 改成 publish / wiki_only / ignore，然后再次运行 finalize。",
        "items": [
            {
                "item_id": entry["item_id"],
                "title": entry["title"],
                "suggested_decision": entry["suggested_decision"],
                "decision": "pending",
                "note": "",
            }
            for entry in review.get("items", [])
        ],
    }
    write_json_file(Path(root) / "review" / f"{run_date}-selection.json", selection)
    return selection


def run_review_stage(root: str | Path, run_date: str) -> dict[str, Any]:
    root = Path(root)
    items, pool = load_decision_pool(root, run_date)
    config_path = root / "harness" / "run-config.yaml"
    config = load_run_config(config_path) if config_path.exists() else DEFAULT_RUN_CONFIG
    review = build_review(run_date, items, global_budget=config.get("global_budget", {}))
    review["summary"]["decision_pool"] = pool
    write_json_file(root / "review" / f"{run_date}-review.json", review)
    (root / "review" / f"{run_date}-review.md").write_text(render_review_markdown(review), encoding="utf-8")
    initialize_selection(root, run_date, review)
    return {
        "status": "selection_required",
        "date": run_date,
        "review": str(root / "review" / f"{run_date}-review.md"),
        "selection": str(root / "review" / f"{run_date}-selection.json"),
    }


def _step(status: str, path: Path | None = None, **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"status": status}
    if path is not None:
        result["path"] = str(path)
    result.update(extra)
    return result


def workflow_status(root: str | Path, run_date: str) -> dict[str, Any]:
    root = Path(root)
    review_path = root / "review" / f"{run_date}-review.json"
    selection_path = root / "review" / f"{run_date}-selection.json"
    result_path = root / "review" / f"{run_date}-workflow-result.json"
    memory_path = root / "memory" / "pending" / f"{run_date}.json"
    article_dir = root / "articles" / run_date
    article_paths = [article_dir / name for name in ["canonical.md", "wechat.md", "zhihu.md", "csdn.md"]]

    review = load_json_file(review_path, {})
    selection = load_json_file(selection_path, {})
    result = load_json_file(result_path, {})
    memory = load_json_file(memory_path, {})

    selection_items = selection.get("items", [])
    pending_decisions = sum(1 for item in selection_items if item.get("decision") == "pending")
    decided_items = sum(1 for item in selection_items if item.get("decision") in DECISIONS)
    article_done = bool(article_paths) and all(path.exists() and path.stat().st_size > 0 for path in article_paths)
    memory_exists = memory_path.exists()
    memory_count = len(memory.get("items", [])) if isinstance(memory, dict) else 0

    steps = {
        "review": _step("done" if review_path.exists() else "missing", review_path),
        "selection": _step(
            "pending" if pending_decisions else ("done" if decided_items or selection_items == [] and selection_path.exists() else "missing"),
            selection_path,
            pending=pending_decisions,
            decided=decided_items,
        ),
        "articles": _step("done" if article_done else "missing", article_dir),
        "memory": _step("done" if memory_exists else "missing", memory_path, count=memory_count),
        "result": _step("done" if result_path.exists() else "missing", result_path),
    }

    if pending_decisions:
        status = "waiting_for_human"
    elif result_path.exists() and article_done and memory_exists:
        status = "complete"
    elif review_path.exists() and selection_path.exists():
        status = "ready_to_finalize"
    elif review_path.exists():
        status = "selection_required"
    else:
        status = "not_started"

    return {
        "date": run_date,
        "status": status,
        "steps": steps,
        "pending_decisions": pending_decisions,
        "decided_items": decided_items,
        "published_count": int(result.get("published_count", 0) or 0) if isinstance(result, dict) else 0,
        "memory_pending_count": int(result.get("memory_pending_count", memory_count) or 0) if isinstance(result, dict) else memory_count,
    }


def _selection_map(root: Path, run_date: str) -> dict[str, dict[str, Any]]:
    selection = load_json_file(root / "review" / f"{run_date}-selection.json", {})
    entries = selection.get("items", [])
    pending = [entry for entry in entries if entry.get("decision") == "pending"]
    invalid = [entry for entry in entries if entry.get("decision") not in DECISIONS and entry.get("decision") != "pending"]
    if pending:
        raise ValueError(f"selection has pending decisions: {', '.join(entry.get('item_id', '') for entry in pending)}")
    if invalid:
        raise ValueError(f"selection has invalid decisions: {', '.join(entry.get('item_id', '') for entry in invalid)}")
    return {entry["item_id"]: entry for entry in entries}


def _selected_items(items: list[dict[str, Any]], selection: dict[str, dict[str, Any]], decision: str) -> list[dict[str, Any]]:
    return [item for item in items if selection.get(item["id"], {}).get("decision") == decision]


def _sources_block(items: list[dict[str, Any]]) -> list[str]:
    lines = ["## 参考来源", ""]
    for item in items:
        lines += [f"- [{item.get('title', 'Untitled')}]({item.get('url')})（{item.get('source_id', 'unknown')}，内容日期：{item.get('content_date') or '未知'}）"]
    return lines


def _canonical_article(run_date: str, publish_items: list[dict[str, Any]]) -> str:
    title = _article_title(publish_items)
    lines = [f"# {title}", "", f"日期：{run_date}", "", "## 今天最值得写的变化", ""]
    for item in publish_items:
        lines += [
            f"### {item.get('title', 'Untitled')}",
            "",
            item.get("summary", ""),
            "",
            item.get("why_it_matters", ""),
            "",
        ]
    lines += ["## 我的判断", "", "这些信号值得持续跟踪，因为它们共同指向 AI 工具、工作流和学习方式的变化。", ""]
    lines += _sources_block(publish_items)
    return "\n".join(lines).strip() + "\n"


def _article_title(items: list[dict[str, Any]]) -> str:
    if not items:
        return "今日 AI Radar"
    first = items[0].get("title", "AI 前沿变化")
    return f"从 {first} 看今天的 AI 前沿变化"


def _wechat_article(run_date: str, publish_items: list[dict[str, Any]]) -> str:
    title = _article_title(publish_items)
    lines = [
        f"# {title}",
        "",
        '<p style="font-size:18px;line-height:1.75;">今天的 AI Radar 里，我最想记录的是下面这些变化。</p>',
        "",
    ]
    for item in publish_items:
        lines += [
            f"## {item.get('title', 'Untitled')}",
            "",
            f'<p style="font-size:18px;line-height:1.75;">{item.get("summary", "")}</p>',
            "",
            f'<blockquote style="border-left:4px solid #16a34a;padding-left:12px;color:#166534;">{item.get("why_it_matters", "")}</blockquote>',
            "",
        ]
    lines += [
        "## 朋友圈配文",
        "",
        f"今天的 AI Radar：{title}。不是简单看新闻，而是把信号沉淀成下一篇文章和下一次学习的素材。",
        "",
        "## 核心配图 Prompt",
        "",
        "一张简洁的 AI 信息雷达工作台，中文科技写作氛围，屏幕上有信息流、人工确认、文章生成、知识沉淀四个步骤，干净明亮，适合公众号封面。",
        "",
    ]
    lines += _sources_block(publish_items)
    return "\n".join(lines).strip() + "\n"


def _zhihu_article(run_date: str, publish_items: list[dict[str, Any]]) -> str:
    title = _article_title(publish_items)
    lines = [f"# {title}", "", "如果只看结论，我认为今天最值得关注的是：", ""]
    for item in publish_items:
        lines += [f"- **{item.get('title', 'Untitled')}**：{item.get('why_it_matters', '')}"]
    lines += ["", "我的理解是，这些内容不只是新闻，更像是下一阶段 AI 工作方式变化的线索。", ""]
    lines += _sources_block(publish_items)
    return "\n".join(lines).strip() + "\n"


def _csdn_article(run_date: str, publish_items: list[dict[str, Any]]) -> str:
    title = _article_title(publish_items)
    lines = [f"# {title}", "", "## 背景", "", "本文整理 AI Radar 今日筛选出的技术动态，并给出可复用的学习与写作线索。", ""]
    for item in publish_items:
        lines += [
            f"## {item.get('title', 'Untitled')}",
            "",
            f"- 来源：{item.get('source_id', 'unknown')}",
            f"- 内容日期：{item.get('content_date') or '未知'}",
            f"- 摘要：{item.get('summary', '')}",
            f"- 技术价值：{item.get('why_it_matters', '')}",
            "",
        ]
    lines += _sources_block(publish_items)
    return "\n".join(lines).strip() + "\n"


def write_article_bundle(root: str | Path, run_date: str, publish_items: list[dict[str, Any]]) -> dict[str, str]:
    root = Path(root)
    article_dir = root / "articles" / run_date
    article_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "canonical": article_dir / "canonical.md",
        "wechat": article_dir / "wechat.md",
        "zhihu": article_dir / "zhihu.md",
        "csdn": article_dir / "csdn.md",
    }
    outputs["canonical"].write_text(_canonical_article(run_date, publish_items), encoding="utf-8")
    outputs["wechat"].write_text(_wechat_article(run_date, publish_items), encoding="utf-8")
    outputs["zhihu"].write_text(_zhihu_article(run_date, publish_items), encoding="utf-8")
    outputs["csdn"].write_text(_csdn_article(run_date, publish_items), encoding="utf-8")
    return {key: str(path) for key, path in outputs.items()}


def _memory_event(item: dict[str, Any], selection_entry: dict[str, Any]) -> dict[str, Any]:
    topic = item.get("content_type") or (item.get("topics") or ["ai_trends"])[0]
    return {
        "source_item_id": item["id"],
        "topic": topic,
        "claim": item.get("summary") or item.get("title"),
        "evidence": {
            "title": item.get("title"),
            "url": item.get("url"),
            "source_id": item.get("source_id"),
            "published_at": item.get("published_at"),
            "content_date": item.get("content_date"),
        },
        "reuse_hint": item.get("why_it_matters") or "后续写 AI 前沿文章时可引用这条资料作为背景。",
        "decision_note": selection_entry.get("note", ""),
        "status": "pending_llm_wiki_ingest",
    }


def write_memory_pending(
    root: str | Path,
    run_date: str,
    wiki_items: list[dict[str, Any]],
    selection: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    payload = {
        "date": run_date,
        "schema": "ai-radar.memory.pending.v0",
        "target": "llm-wiki-interface-reserved",
        "items": [_memory_event(item, selection[item["id"]]) for item in wiki_items],
    }
    write_json_file(Path(root) / "memory" / "pending" / f"{run_date}.json", payload)
    return payload


def finalize_selection(root: str | Path, run_date: str, items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    root = Path(root)
    current_items = items if items is not None else load_json_file(root / "data" / run_date / "items.json", [])
    selection = _selection_map(root, run_date)
    publish_items = _selected_items(current_items, selection, "publish")
    wiki_items = _selected_items(current_items, selection, "wiki_only")
    article_paths = write_article_bundle(root, run_date, publish_items) if publish_items else {}
    memory = write_memory_pending(root, run_date, wiki_items, selection)
    result = {
        "date": run_date,
        "status": "complete",
        "published_count": len(publish_items),
        "memory_pending_count": len(memory["items"]),
        "article_paths": article_paths,
        "memory_pending": str(root / "memory" / "pending" / f"{run_date}.json"),
    }
    write_json_file(root / "review" / f"{run_date}-workflow-result.json", result)
    return result
