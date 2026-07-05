from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_radar.publish_workflow import (
    build_review,
    finalize_selection,
    initialize_selection,
    load_decision_pool,
    run_review_stage,
)
from ai_radar.scoring import fallback_score_item


def _item(
    item_id: str,
    title: str,
    *,
    status: str = "candidate",
    publish_score: int = 4,
    learning_score: int = 4,
    importance: int = 4,
    source_id: str = "test_source",
) -> dict[str, object]:
    return {
        "id": item_id,
        "source_id": source_id,
        "source_type": "company_official",
        "title": title,
        "url": f"https://example.com/{item_id}",
        "summary": f"{title} 的中文摘要",
        "why_it_matters": f"{title} 值得关注，因为它影响 AI 工作流。",
        "content_type": "agent_workflow",
        "publish_score": publish_score,
        "learning_score": learning_score,
        "importance": importance,
        "freshness_score": 4,
        "status": status,
        "article_angles": [f"从 {title} 看 AI 前沿变化"],
        "learning_notes": [f"学习 {title}"],
        "published_at": "2026-07-05T01:00:00+00:00",
        "content_date": "2026-07-05",
        "captured_at": "2026-07-05T09:00:00+08:00",
        "date_confidence": "exact",
    }


def test_build_review_recommends_publish_and_wiki_only():
    review = build_review(
        "2026-07-05",
        [
            _item("2026-07-05-a", "Agent Harness 新实践", publish_score=5, learning_score=5),
            _item("2026-07-05-b", "值得沉淀的研究资料", publish_score=2, learning_score=5),
            _item("2026-07-05-c", "低价值噪声", publish_score=1, learning_score=1, importance=1),
        ],
    )

    decisions = {entry["item_id"]: entry["suggested_decision"] for entry in review["items"]}
    assert decisions["2026-07-05-a"] == "publish"
    assert decisions["2026-07-05-b"] == "wiki_only"
    assert decisions["2026-07-05-c"] == "ignore"
    assert review["summary"]["publish_candidates"] == 1
    assert review["summary"]["wiki_candidates"] == 1


def test_run_review_stage_writes_review_and_pending_selection(tmp_path: Path):
    items_dir = tmp_path / "data" / "2026-07-05"
    items_dir.mkdir(parents=True)
    (items_dir / "items.json").write_text(
        json.dumps([_item("2026-07-05-a", "Agent Harness 新实践")], ensure_ascii=False),
        encoding="utf-8",
    )

    result = run_review_stage(tmp_path, "2026-07-05")

    review = json.loads((tmp_path / "review" / "2026-07-05-review.json").read_text(encoding="utf-8"))
    selection = json.loads((tmp_path / "review" / "2026-07-05-selection.json").read_text(encoding="utf-8"))
    assert result["status"] == "selection_required"
    assert review["items"][0]["item_id"] == "2026-07-05-a"
    assert selection["items"][0]["decision"] == "pending"
    assert selection["items"][0]["suggested_decision"] == "publish"


def test_run_review_stage_filters_evidence_pool_by_content_date(tmp_path: Path):
    items_dir = tmp_path / "data" / "2026-07-05"
    items_dir.mkdir(parents=True)
    (items_dir / "items.json").write_text(
        json.dumps([_item("2026-07-05-a", "Only scored item")], ensure_ascii=False),
        encoding="utf-8",
    )
    evidence_dir = tmp_path / "evidence" / "2026-07-05"
    evidence_dir.mkdir(parents=True)
    (evidence_dir / "andrewng_x.json").write_text(
        json.dumps(
            {
                "source_id": "andrewng_x",
                "records": [
                    {
                        "source_id": "andrewng_x",
                        "source_type": "person_x",
                        "title": "Old Andrew Ng X post",
                        "url": "https://x.com/AndrewYNg/status/1",
                        "author": "andrewng_x",
                        "published_at": "2026-05-01T00:00:00+00:00",
                        "content_date": "2026-05-01",
                        "captured_at": "2026-07-05T09:00:00+08:00",
                        "text": "Andrew Ng talks about prompting.",
                        "raw": {},
                        "topics": ["opinion_signal"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (evidence_dir / "anthropic_blog.json").write_text(
        json.dumps(
            {
                "source_id": "anthropic_blog",
                "records": [
                    {
                        "source_id": "anthropic_blog",
                        "source_type": "company_blog",
                        "title": "Anthropic workflow post",
                        "url": "https://www.anthropic.com/news/workflow",
                        "author": None,
                        "published_at": "2026-07-05T09:00:00+00:00",
                        "content_date": "2026-07-05",
                        "captured_at": "2026-07-05T09:00:00+08:00",
                        "text": "Anthropic writes about workflows.",
                        "raw": {},
                        "topics": ["agent_workflow"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    run_review_stage(tmp_path, "2026-07-05")

    review = json.loads((tmp_path / "review" / "2026-07-05-review.json").read_text(encoding="utf-8"))
    titles = {entry["title"] for entry in review["items"]}
    assert "Old Andrew Ng X post" not in titles
    assert "Anthropic workflow post" in titles
    assert review["summary"]["decision_pool"] == "evidence"


def test_load_decision_pool_collapses_same_source_same_title_evidence(tmp_path: Path):
    evidence_dir = tmp_path / "evidence" / "2026-07-05"
    evidence_dir.mkdir(parents=True)
    records = [
        {
            "source_id": "karpathy_github",
            "source_type": "person_feed",
            "title": "karpathy pushed nanochat",
            "url": f"https://github.com/karpathy/nanochat/compare/{index}",
            "author": "karpathy",
            "published_at": "2026-07-05T01:00:00+00:00",
            "content_date": "2026-07-05",
            "captured_at": "2026-07-05T09:00:00+08:00",
            "text": "Push event for nanochat.",
            "topics": ["opinion_signal", "agent_workflow"],
        }
        for index in range(3)
    ]
    (evidence_dir / "karpathy_github.json").write_text(
        json.dumps({"source_id": "karpathy_github", "records": records}, ensure_ascii=False),
        encoding="utf-8",
    )

    items, pool = load_decision_pool(tmp_path, "2026-07-05")

    assert pool == "evidence"
    assert [item["title"] for item in items].count("karpathy pushed nanochat") == 1


def test_fallback_summary_names_specific_subject_instead_of_generic_template():
    item = fallback_score_item(
        {
            "source_id": "karpathy_github",
            "source_type": "person_feed",
            "title": "karpathy pushed nanochat",
            "url": "https://github.com/karpathy/nanochat/compare/1",
            "author": "karpathy",
            "published_at": "2026-07-05T01:00:00+00:00",
            "content_date": "2026-07-05",
            "captured_at": "2026-07-05T09:00:00+08:00",
            "text": "Push event for nanochat.",
            "topics": ["opinion_signal", "agent_workflow"],
        },
        "2026-07-05",
    )

    assert "nanochat" in item["summary"]
    assert "GitHub" in item["summary"]
    assert "这条内容主要讲行业观点和趋势信号" not in item["summary"]


def test_finalize_selection_requires_human_decisions(tmp_path: Path):
    items = [_item("2026-07-05-a", "Agent Harness 新实践")]
    initialize_selection(tmp_path, "2026-07-05", build_review("2026-07-05", items))

    with pytest.raises(ValueError, match="pending"):
        finalize_selection(tmp_path, "2026-07-05", items)


def test_finalize_selection_generates_articles_and_memory_pending(tmp_path: Path):
    items = [
        _item("2026-07-05-a", "Agent Harness 新实践", publish_score=5, learning_score=5),
        _item("2026-07-05-b", "值得沉淀的研究资料", publish_score=2, learning_score=5),
    ]
    review = build_review("2026-07-05", items)
    initialize_selection(tmp_path, "2026-07-05", review)
    selection_path = tmp_path / "review" / "2026-07-05-selection.json"
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    selection["items"][0]["decision"] = "publish"
    selection["items"][1]["decision"] = "wiki_only"
    selection_path.write_text(json.dumps(selection, ensure_ascii=False, indent=2), encoding="utf-8")

    result = finalize_selection(tmp_path, "2026-07-05", items)

    article_dir = tmp_path / "articles" / "2026-07-05"
    assert result["status"] == "complete"
    assert (article_dir / "canonical.md").exists()
    assert (article_dir / "wechat.md").exists()
    assert (article_dir / "zhihu.md").exists()
    assert (article_dir / "csdn.md").exists()
    assert "Agent Harness 新实践" in (article_dir / "wechat.md").read_text(encoding="utf-8")
    memory = json.loads((tmp_path / "memory" / "pending" / "2026-07-05.json").read_text(encoding="utf-8"))
    assert memory["items"][0]["source_item_id"] == "2026-07-05-b"
    assert memory["items"][0]["reuse_hint"]


def test_build_review_uses_recommended_action_and_excludes_archive():
    items = [
        {**_item("a", "Publish item"), "recommended_action": "publish", "status": "candidate"},
        {**_item("b", "Wiki item"), "recommended_action": "wiki_only", "status": "candidate"},
        {**_item("c", "Archived item"), "recommended_action": "ignore", "status": "archive"},
    ]

    review = build_review("2026-07-05", items)

    assert [entry["item_id"] for entry in review["items"]] == ["a", "b"]
    assert review["items"][0]["suggested_decision"] == "publish"
    assert review["items"][1]["suggested_decision"] == "wiki_only"


def test_build_review_respects_max_human_review_items():
    items = [
        {**_item(f"item-{index}", f"Item {index}"), "daily_rank": float(index), "source_priority": "high"}
        for index in range(5)
    ]

    review = build_review("2026-07-05", items, global_budget={"max_human_review_items": 2})

    assert review["summary"]["total_items"] == 2
    assert [entry["item_id"] for entry in review["items"]] == ["item-4", "item-3"]
    assert review["summary"]["budget_evicted"]["count"] == 3
