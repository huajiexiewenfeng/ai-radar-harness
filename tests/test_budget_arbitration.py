from __future__ import annotations

from ai_radar.budget import apply_global_human_budget, apply_source_candidate_budget, source_tier
from ai_radar.scoring import score_records


def _item(item_id: str, source_id: str, priority: str, rank: float, published_at: str = "2026-07-05T00:00:00+00:00"):
    return {
        "id": item_id,
        "source_id": source_id,
        "source_priority": priority,
        "daily_rank": rank,
        "published_at": published_at,
        "status": "candidate",
        "human_gate_eligible": True,
    }


def test_source_tier_orders_priority():
    assert source_tier({"priority": "high"}) > source_tier({"priority": "medium"})
    assert source_tier({"priority": "medium"}) > source_tier({"priority": "low"})


def test_apply_source_candidate_budget_respects_daily_limit_and_high_noise_halving():
    source = {
        "id": "elonmusk_x",
        "source_budget": {"daily_candidate_limit": 3, "noise_level": "high"},
    }
    records = [{"url": f"https://x.com/1/{index}", "prefilter_decision": "candidate"} for index in range(5)]

    kept, stats = apply_source_candidate_budget(source, records)

    assert len(kept) == 1
    assert stats["source_candidate_evicted"] == 4


def test_apply_global_human_budget_archives_evicted_items():
    items = [
        _item("a", "openai_news", "high", 4.0),
        _item("b", "meta_ai_blog", "medium", 5.0),
        _item("c", "papers", "low", 5.0),
    ]

    kept, stats = apply_global_human_budget(items, {"max_human_review_items": 2})

    assert [item["id"] for item in kept] == ["a", "b"]
    assert stats["budget_evicted"]["count"] == 1
    assert stats["budget_evicted"]["items"] == ["c"]


def test_score_records_adds_recommended_action_and_source_priority():
    records = [
        {
            "source_id": "openai_news",
            "source_type": "company_blog",
            "source_priority": "high",
            "title": "Introducing a new model",
            "url": "https://example.com/model",
            "text": "model release",
            "topics": ["model_release"],
            "captured_at": "2026-07-05T09:00:00+08:00",
            "published_at": "2026-07-05T01:00:00+00:00",
            "content_date": "2026-07-05",
        }
    ]

    items, stats = score_records(records, "2026-07-05", limit=10, llm_config={"provider": "none"})

    assert items[0]["recommended_action"] == "publish"
    assert items[0]["source_priority"] == "high"
    assert stats["estimated_input_tokens"] > 0


def test_score_records_marks_pending_after_token_budget():
    long_text = "agent " * 2000
    records = [
        {
            "source_id": "a",
            "source_type": "company_blog",
            "title": f"Agent workflow {index}",
            "url": f"https://example.com/{index}",
            "text": long_text,
            "captured_at": "2026-07-05T09:00:00+08:00",
            "published_at": "2026-07-05T01:00:00+00:00",
            "content_date": "2026-07-05",
        }
        for index in range(3)
    ]

    items, stats = score_records(
        records,
        "2026-07-05",
        limit=10,
        llm_config={"provider": "none", "max_llm_tokens_per_run": 100},
    )

    assert stats["token_budget_exceeded"] >= 1
    assert any(item["summary"] == "pending" for item in items)
