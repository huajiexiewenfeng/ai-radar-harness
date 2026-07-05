from __future__ import annotations

from ai_radar.runner import apply_phase1_record_controls


def test_apply_phase1_record_controls_enriches_and_filters_records(tmp_path):
    sources = [
        {
            "id": "active_blog",
            "type": "company_blog",
            "status": "active",
            "priority": "high",
            "dedupe_mode": "link",
            "source_budget": {"daily_candidate_limit": 1, "noise_level": "low"},
        },
        {
            "id": "probation_x",
            "type": "person_x",
            "status": "probation",
            "priority": "medium",
            "dedupe_mode": "link",
            "source_budget": {"daily_candidate_limit": 5, "noise_level": "medium"},
        },
    ]
    records = [
        {"source_id": "active_blog", "title": "agent workflow one", "text": "agent workflow", "url": "https://example.com/1"},
        {"source_id": "active_blog", "title": "agent workflow two", "text": "agent workflow", "url": "https://example.com/2"},
        {"source_id": "probation_x", "title": "agent workflow", "text": "agent workflow", "url": "https://x.com/a/1"},
    ]
    keywords = {"include": ["agent"], "exclude": []}

    kept, stats = apply_phase1_record_controls(records, sources, keywords)

    assert [record["url"] for record in kept] == ["https://example.com/1", "https://x.com/a/1"]
    assert kept[0]["human_gate_eligible"] is True
    assert kept[1]["human_gate_eligible"] is False
    assert stats["by_source"]["active_blog"]["source_candidate_evicted"] == 1
    assert stats["by_source"]["probation_x"]["probation_records"] == 1
