from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any

from ai_radar.timeutil import freshness_score
from ai_radar.urlutil import item_id_for


CONFIDENCE_WEIGHTS = {"source_backed": 5, "inferred": 3, "low_confidence": 1}

TOPIC_LABELS = {
    "agent_workflow": "Agent 工作流",
    "developer_tooling": "开发者工具",
    "infra_tooling": "基础设施",
    "model_release": "模型发布",
    "research_release": "研究进展",
    "benchmark_eval": "评测基准",
    "learning_reference": "学习参考",
    "opinion_signal": "行业观点",
    "ai_trends": "AI 趋势",
    "safety": "安全治理",
}


def confidence_weight(value: str) -> int:
    return CONFIDENCE_WEIGHTS.get(value, 1)


def infer_content_type(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ["agent", "workflow", "harness", "tool use"]):
        return "agent_workflow"
    if any(word in lowered for word in ["model", "release", "api"]):
        return "model_release"
    if any(word in lowered for word in ["paper", "research", "arxiv"]):
        return "research_release"
    return "opinion_signal"


def _topic_labels(record: dict[str, Any], content_type: str) -> list[str]:
    topics = record.get("topics") or []
    labels = [TOPIC_LABELS.get(topic, topic) for topic in topics if topic]
    primary = TOPIC_LABELS.get(content_type, content_type)
    if primary not in labels:
        labels.insert(0, primary)
    return labels[:3]


def _source_label(source_type: str | None, source_id: str | None) -> str:
    value = source_type or ""
    if value.startswith("person"):
        return "来自 AI 圈人物动态"
    if value.startswith("company"):
        return "来自公司官方动态"
    if value.startswith("engineering"):
        return "来自工程实践文章"
    if value.startswith("research"):
        return "来自研究趋势源"
    return f"来自 {source_id or '已配置来源'}"


def _keyword_focus(text: str, content_type: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ["cost", "bill", "spend", "budget"]):
        return "成本、可观测性和治理"
    if any(word in lowered for word in ["memory", "remember", "context"]):
        return "长期记忆和上下文管理"
    if any(word in lowered for word in ["skill", "tool use", "tool"]):
        return "技能、工具调用和 Agent 可靠性"
    if any(word in lowered for word in ["prompt", "programming", "coding"]):
        return "提示词、编程和人机协作方式"
    if any(word in lowered for word in ["release", "available", "introducing", "launch"]):
        return "新能力发布和产品落地"
    if content_type == "agent_workflow":
        return "Agent 工作流设计"
    if content_type == "model_release":
        return "模型能力变化"
    if content_type == "research_release":
        return "研究方法和技术路线"
    return "行业观点和趋势信号"


def _source_entity(source_id: str | None, source_type: str | None) -> str:
    value = (source_id or "").lower()
    if "karpathy" in value:
        return "Karpathy"
    if "andrew" in value or "andrewng" in value:
        return "Andrew Ng"
    if "anthropic" in value:
        return "Anthropic"
    if "openai" in value:
        return "OpenAI"
    if "deepmind" in value or "google" in value:
        return "Google DeepMind"
    if "langchain" in value:
        return "LangChain"
    if source_type and source_type.startswith("person"):
        return "AI 圈人物"
    if source_type and source_type.startswith("company"):
        return "公司官方"
    return source_id or "该来源"


def _compact_snippet(text: str, limit: int = 72) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _github_repo(url: str) -> str | None:
    match = re.search(r"github\.com/([^/]+/[^/?#]+)", url)
    if not match:
        return None
    return match.group(1)


def _specific_summary(record: dict[str, Any], content_type: str) -> str:
    title = str(record.get("title") or "这条内容").strip()
    text = str(record.get("text") or "").strip()
    url = str(record.get("url") or "")
    source_id = record.get("source_id")
    source_type = record.get("source_type")
    entity = _source_entity(source_id, source_type)
    combined = " ".join([title, text]).lower()
    snippet = _compact_snippet(text if text and len(text) > len(title) else title)

    repo = _github_repo(url)
    if repo:
        action = "新的 GitHub 动态"
        if "pushed" in combined or "push" in combined:
            action = "新的 push 动态"
        elif "pull request" in combined or " pr " in f" {combined} ":
            action = "新的 PR 动态"
        return f"{entity} 在 GitHub 仓库 {repo} 有{action}，更适合作为项目迭代线索合并跟踪。"

    if any(word in combined for word in ["cost", "bill", "spend", "budget"]):
        return f"{entity} 这条内容聚焦「{snippet}」，重点是 AI/Agent 使用成本、账单或预算治理。"
    if any(word in combined for word in ["workflow", "harness", "agent"]):
        return f"{entity} 这条内容聚焦「{snippet}」，可用于判断 Agent 工作流和工程实践的新变化。"
    if any(word in combined for word in ["claude", "gpt", "gemini", "model", "release", "available", "introducing", "launch"]):
        return f"{entity} 这条内容聚焦「{snippet}」，属于模型、产品能力或发布节奏线索。"
    if any(word in combined for word in ["paper", "research", "arxiv", "benchmark"]):
        return f"{entity} 这条内容聚焦「{snippet}」，适合沉淀为研究进展或学习参考。"
    if str(source_type or "").startswith("person"):
        return f"{entity} 的动态围绕「{snippet}」，适合判断 AI 圈人物正在关注什么。"
    if str(source_type or "").startswith("company"):
        return f"{entity} 官方动态围绕「{snippet}」，可用于跟踪公司产品、研究或政策变化。"
    if content_type == "agent_workflow":
        return f"这条内容围绕「{snippet}」，可用于判断 Agent 工作流实践是否出现新方法。"
    return f"这条内容围绕「{snippet}」，可作为后续筛选和人工判断的具体线索。"


def chinese_summary(record: dict[str, Any], content_type: str) -> str:
    labels = "、".join(_topic_labels(record, content_type))
    return f"{_specific_summary(record, content_type)} 主题：{labels}。"


def why_it_matters(record: dict[str, Any], content_type: str, importance: int, publish_score: int, learning_score: int) -> str:
    combined = " ".join([record.get("title", ""), record.get("text", "")])
    focus = _keyword_focus(combined, content_type)
    source = _source_label(record.get("source_type"), record.get("source_id"))
    if content_type == "agent_workflow":
        reason = f"它把焦点落在{focus}，直接关系到 Agent 如何拆任务、用工具、控成本或沉淀经验，能帮助我们更新 workflow harness 的实践判断。"
    elif content_type == "model_release":
        reason = f"它把焦点落在{focus}，可能改变模型能力边界、可用场景或产品节奏，适合作为公司动态和选题线索。"
    elif content_type == "research_release":
        reason = f"它把焦点落在{focus}，提供了新的方法、基准或实验方向，适合放进个人学习雷达持续跟踪。"
    else:
        reason = f"它反映了{focus}上的一线观点，适合用来判断 AI 圈正在讨论什么。"
    score_hint = f"发布价值 {publish_score}/5，学习价值 {learning_score}/5。"
    return f"{source}；{reason}{score_hint}"


def recommended_action(item: dict[str, Any]) -> str:
    if item.get("status") in {"archive", "ignore", "unscored"}:
        return "ignore"
    if int(item.get("publish_score", 0) or 0) >= 4 and int(item.get("importance", 0) or 0) >= 3:
        return "publish"
    if int(item.get("learning_score", 0) or 0) >= 4:
        return "wiki_only"
    return "ignore"


def estimate_input_tokens(record: dict[str, Any]) -> int:
    text = " ".join([str(record.get("title") or ""), str(record.get("text") or "")])
    return max(1, len(text) // 4)


def fallback_score_item(record: dict[str, Any], run_date: str, unscored: bool = False) -> dict[str, Any]:
    text = " ".join([record.get("title", ""), record.get("text", "")]).strip()
    content_type = infer_content_type(text)
    published_at = record.get("published_at")
    captured_at_text = record.get("captured_at")
    captured_at = datetime.fromisoformat(captured_at_text) if captured_at_text else None
    fresh = freshness_score(published_at, captured_at)
    importance = 4 if content_type in {"agent_workflow", "model_release", "research_release"} else 3
    publish_score = 4 if content_type in {"agent_workflow", "model_release", "opinion_signal"} else 3
    learning_score = 5 if content_type in {"agent_workflow", "research_release", "learning_reference"} else 3
    title = record.get("title", "Untitled")
    item = {
        "id": item_id_for(run_date, record["url"]),
        "source_id": record.get("source_id"),
        "source_type": record.get("source_type"),
        "source_priority": record.get("source_priority", record.get("priority", "low")),
        "title": title,
        "url": record["url"],
        "author": record.get("author"),
        "published_at": published_at,
        "content_date": record.get("content_date"),
        "date_confidence": record.get("date_confidence", "unknown"),
        "captured_at": captured_at_text,
        "summary": "pending" if unscored else chinese_summary(record, content_type),
        "why_it_matters": "pending" if unscored else why_it_matters(record, content_type, importance, publish_score, learning_score),
        "topics": record.get("topics") or [],
        "content_type": content_type,
        "importance": importance,
        "publish_score": publish_score,
        "learning_score": learning_score,
        "freshness_score": fresh,
        "confidence": "source_backed" if record.get("url") else "low_confidence",
        "platform_fit": ["wechat", "zhihu", "csdn"],
        "article_angles": [f"从 {title} 看 AI 前沿的新变化"],
        "learning_notes": [f"补充理解：{title}"],
        "status": "unscored" if unscored else "candidate",
        "human_gate_eligible": record.get("human_gate_eligible", True),
        "prefilter_decision": record.get("prefilter_decision", "candidate"),
        "prefilter_reason": record.get("prefilter_reason"),
    }
    item["recommended_action"] = recommended_action(item)
    if item["recommended_action"] == "ignore":
        item["status"] = "archive"
    return item


def daily_rank(item: dict[str, Any]) -> float:
    return item["importance"] * 0.4 + item["publish_score"] * 0.4 + item["freshness_score"] * 0.2


def learning_rank(item: dict[str, Any]) -> float:
    return item["learning_score"] * 0.5 + item["importance"] * 0.3 + confidence_weight(item["confidence"]) * 0.2


def _select_with_person_reserve(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    selected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    best_person_by_source: dict[str, dict[str, Any]] = {}
    for item in items:
        if str(item.get("source_type", "")).startswith("person"):
            source_id = str(item.get("source_id", ""))
            if source_id and source_id not in best_person_by_source:
                best_person_by_source[source_id] = item
    for item in best_person_by_source.values():
        selected.append(item)
        seen_ids.add(item["id"])
        if len(selected) >= limit:
            return selected
    for item in items:
        if item["id"] in seen_ids:
            continue
        selected.append(item)
        seen_ids.add(item["id"])
        if len(selected) >= limit:
            break
    selected.sort(key=lambda item: item.get("daily_rank", 0), reverse=True)
    return selected


def _should_use_llm(llm_config: dict[str, Any]) -> bool:
    provider = llm_config.get("provider", "none")
    if provider == "none":
        return False
    api_key_env = llm_config.get("api_key_env", "AI_RADAR_LLM_KEY")
    return bool(os.environ.get(api_key_env))


def score_records(
    records: list[dict[str, Any]],
    run_date: str,
    limit: int,
    llm_config: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    use_llm = _should_use_llm(llm_config)
    unscored = llm_config.get("provider", "none") != "none" and not use_llm
    token_limit = int(llm_config.get("max_llm_tokens_per_run", 200000) or 200000)
    estimated_total = 0
    prepared_records: list[tuple[dict[str, Any], bool]] = []
    token_budget_exceeded = 0
    for record in records:
        record_tokens = estimate_input_tokens(record)
        if estimated_total + record_tokens > token_limit:
            prepared_records.append((record, True))
            token_budget_exceeded += 1
            continue
        estimated_total += record_tokens
        prepared_records.append((record, unscored))
    items = [fallback_score_item(record, run_date, unscored=record_unscored) for record, record_unscored in prepared_records]
    for item in items:
        item["daily_rank"] = daily_rank(item)
        item["learning_rank"] = learning_rank(item)
    items.sort(key=lambda item: item["daily_rank"], reverse=True)
    selected = _select_with_person_reserve(items, limit)
    return selected, {
        "llm_calls": 0,
        "llm_failures": len(selected) if unscored else 0,
        "unscored": len([item for item in selected if item.get("status") == "unscored"]),
        "estimated_input_tokens": estimated_total,
        "token_budget_exceeded": token_budget_exceeded,
    }
