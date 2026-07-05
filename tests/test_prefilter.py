from __future__ import annotations

from pathlib import Path

from ai_radar.prefilter import load_keywords, prefilter_record


def test_load_keywords_reads_include_and_exclude(tmp_path: Path):
    path = tmp_path / "keywords.yaml"
    path.write_text(
        """
include: [agent, model]
exclude: [webinar, hiring]
""",
        encoding="utf-8",
    )

    keywords = load_keywords(path)

    assert keywords["include"] == ["agent", "model"]
    assert keywords["exclude"] == ["webinar", "hiring"]


def test_high_noise_requires_ai_keyword_and_discards_retweet():
    source = {
        "id": "elonmusk_x",
        "status": "active",
        "source_budget": {"noise_level": "high"},
    }
    keywords = {"include": ["agent", "model"], "exclude": ["webinar"]}

    retweet = {"title": "model launch", "text": "new model", "raw": {"is_retweet": True}}
    off_topic = {"title": "random life update", "text": "nothing technical", "raw": {}}
    useful = {"title": "agent tooling", "text": "new agent workflow", "raw": {}}

    assert prefilter_record(retweet, source, keywords)["decision"] == "discard"
    assert prefilter_record(off_topic, source, keywords)["decision"] == "discard"
    assert prefilter_record(useful, source, keywords)["decision"] == "candidate"


def test_exclude_keyword_archives_marketing_content():
    source = {
        "id": "demo_blog",
        "status": "active",
        "source_budget": {"noise_level": "medium"},
    }
    keywords = {"include": ["agent"], "exclude": ["webinar"]}
    record = {"title": "agent webinar registration", "text": "join our webinar", "raw": {}}

    result = prefilter_record(record, source, keywords)

    assert result["decision"] == "archive"
    assert result["reason"] == "exclude_keyword"


def test_probation_source_goes_to_observation_not_human_gate():
    source = {
        "id": "new_source",
        "status": "probation",
        "source_budget": {"noise_level": "low"},
    }
    keywords = {"include": ["agent"], "exclude": []}
    record = {"title": "agent workflow", "text": "agent workflow", "raw": {}}

    result = prefilter_record(record, source, keywords)

    assert result["decision"] == "candidate"
    assert result["human_gate_eligible"] is False
    assert result["reason"] == "probation"
