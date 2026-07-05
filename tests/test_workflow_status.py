from __future__ import annotations

import json
from pathlib import Path

from ai_radar.health import evaluate_run_health
from ai_radar.publish_workflow import workflow_status
from ai_radar.render import render_dashboard_data


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_workflow_status_reports_stage_progress(tmp_path: Path):
    run_date = "2026-07-05"
    _write_json(tmp_path / "review" / f"{run_date}-review.json", {"items": [{"item_id": "a"}]})
    _write_json(
        tmp_path / "review" / f"{run_date}-selection.json",
        {"items": [{"item_id": "a", "decision": "pending"}]},
    )

    status = workflow_status(tmp_path, run_date)

    assert status["status"] == "waiting_for_human"
    assert status["steps"]["review"]["status"] == "done"
    assert status["steps"]["selection"]["status"] == "pending"
    assert status["steps"]["articles"]["status"] == "missing"
    assert status["pending_decisions"] == 1


def test_workflow_status_pending_selection_overrides_stale_result(tmp_path: Path):
    run_date = "2026-07-05"
    _write_json(
        tmp_path / "review" / f"{run_date}-selection.json",
        {"items": [{"item_id": "a", "decision": "pending"}]},
    )
    _write_json(tmp_path / "review" / f"{run_date}-workflow-result.json", {"published_count": 1})
    _write_json(tmp_path / "memory" / "pending" / f"{run_date}.json", {"items": []})
    article_dir = tmp_path / "articles" / run_date
    article_dir.mkdir(parents=True)
    for name in ["canonical.md", "wechat.md", "zhihu.md", "csdn.md"]:
        (article_dir / name).write_text("stale", encoding="utf-8")

    status = workflow_status(tmp_path, run_date)

    assert status["status"] == "waiting_for_human"


def test_render_dashboard_data_includes_workflow_status(tmp_path: Path):
    run_date = "2026-07-05"
    _write_json(tmp_path / "review" / f"{run_date}-workflow-result.json", {"published_count": 1, "memory_pending_count": 2})
    _write_json(tmp_path / "memory" / "pending" / f"{run_date}.json", {"items": [{}, {}]})
    article_dir = tmp_path / "articles" / run_date
    article_dir.mkdir(parents=True)
    for name in ["canonical.md", "wechat.md", "zhihu.md", "csdn.md"]:
        (article_dir / name).write_text("ok", encoding="utf-8")

    data = render_dashboard_data(run_date, [], {}, {}, [], root=tmp_path)

    assert '"workflow"' in data
    assert '"status": "complete"' in data
    assert '"memory_pending_count": 2' in data


def test_render_dashboard_data_includes_human_selection_queue(tmp_path: Path):
    run_date = "2026-07-05"
    _write_json(
        tmp_path / "review" / f"{run_date}-review.json",
        {
            "items": [
                {
                    "item_id": "item-a",
                    "title": "值得发文的素材",
                    "suggested_decision": "publish",
                    "reason": "适合作为今日主素材。",
                    "summary": "中文摘要",
                    "url": "https://example.com/a",
                    "source_id": "test",
                }
            ]
        },
    )
    _write_json(
        tmp_path / "review" / f"{run_date}-selection.json",
        {
            "items": [
                {
                    "item_id": "item-a",
                    "title": "值得发文的素材",
                    "suggested_decision": "publish",
                    "decision": "pending",
                    "note": "",
                }
            ]
        },
    )

    data = render_dashboard_data(run_date, [], {}, {}, [], root=tmp_path)

    assert '"human_selection"' in data
    assert '"item_id": "item-a"' in data
    assert '"decision": "pending"' in data
    assert '"reason": "适合作为今日主素材。"' in data


def test_render_dashboard_data_includes_decision_summary_layer(tmp_path: Path):
    run_date = "2026-07-05"
    _write_json(
        tmp_path / "review" / f"{run_date}-review.json",
        {
            "items": [
                {
                    "item_id": "item-a",
                    "title": "发文素材",
                    "suggested_decision": "publish",
                    "reason": "适合发文。",
                    "summary": "摘要 A",
                    "url": "https://example.com/a",
                    "source_id": "andrewng_x",
                    "content_date": "2026-07-05",
                },
                {
                    "item_id": "item-b",
                    "title": "沉淀素材",
                    "suggested_decision": "wiki_only",
                    "reason": "适合沉淀。",
                    "summary": "摘要 B",
                    "url": "https://example.com/b",
                    "source_id": "anthropic_blog",
                    "content_date": None,
                },
            ]
        },
    )
    _write_json(
        tmp_path / "review" / f"{run_date}-selection.json",
        {
            "items": [
                {"item_id": "item-a", "title": "发文素材", "suggested_decision": "publish", "decision": "pending", "note": ""},
                {"item_id": "item-b", "title": "沉淀素材", "suggested_decision": "wiki_only", "decision": "wiki_only", "note": ""},
            ]
        },
    )

    data = render_dashboard_data(run_date, [], {}, {}, [], root=tmp_path)

    assert '"decision_summary"' in data
    assert '"total": 2' in data
    assert '"publish": 1' in data
    assert '"wiki_only": 1' in data
    assert '"unknown_date": 1' in data
    assert '"andrewng_x": 1' in data
    assert '"anthropic_blog": 1' in data


def test_health_includes_publish_workflow_goal(tmp_path: Path):
    run_date = "2026-07-05"
    _write_json(tmp_path / "data" / run_date / "items.json", [{"learning_score": 1, "source_type": "person_x", "source_id": "x"}])
    (tmp_path / "drafts").mkdir()
    (tmp_path / "drafts" / f"{run_date}-topics.md").write_text("topics", encoding="utf-8")
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / f"{run_date}-ai-radar.md").write_text("## 前沿知识学习池\n## 公司与人物动态", encoding="utf-8")
    (tmp_path / "dashboard").mkdir()
    (tmp_path / "dashboard" / "index.html").write_text("html", encoding="utf-8")
    (tmp_path / "dashboard" / "dashboard-data.js").write_text("js", encoding="utf-8")
    _write_json(tmp_path / "harness" / "trace" / f"{run_date}-run.json", {"x_status": "ok"})
    _write_json(tmp_path / "review" / f"{run_date}-workflow-result.json", {"published_count": 1, "memory_pending_count": 1})
    _write_json(tmp_path / "memory" / "pending" / f"{run_date}.json", {"items": [{}]})
    article_dir = tmp_path / "articles" / run_date
    article_dir.mkdir(parents=True)
    for name in ["canonical.md", "wechat.md", "zhihu.md", "csdn.md"]:
        (article_dir / name).write_text("ok", encoding="utf-8")

    health = evaluate_run_health(tmp_path, run_date, require_x=True)

    assert health["goals"]["publish_workflow"]["status"] == "ok"
    assert health["status"] == "ok"
