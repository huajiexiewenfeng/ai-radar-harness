from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_radar.workflow_harness import continue_after_human, run_until_human


def test_run_until_human_stops_after_selection(monkeypatch, tmp_path: Path):
    calls: list[str] = []

    def fake_run_live(root, run_date, since_hours, limit, filter_by_content_date=False):
        calls.append("collect")
        return {"status": "complete", "item_count": 1}

    def fake_run_review_stage(root, run_date):
        calls.append("review")
        review_dir = Path(root) / "review"
        review_dir.mkdir(parents=True)
        (review_dir / f"{run_date}-selection.json").write_text(
            json.dumps({"items": [{"item_id": "a", "decision": "pending"}]}),
            encoding="utf-8",
        )
        return {"status": "selection_required"}

    monkeypatch.setattr("ai_radar.workflow_harness.run_live", fake_run_live)
    monkeypatch.setattr("ai_radar.workflow_harness.run_review_stage", fake_run_review_stage)

    result = run_until_human(tmp_path, "2026-07-05", since_hours=48, limit=30)

    assert calls == ["collect", "review"]
    assert result["harness_status"] == "human_gate_required"
    assert result["workflow"]["status"] == "waiting_for_human"


def test_continue_after_human_refuses_pending_selection(tmp_path: Path):
    review_dir = tmp_path / "review"
    review_dir.mkdir(parents=True)
    (review_dir / "2026-07-05-selection.json").write_text(
        json.dumps({"items": [{"item_id": "a", "decision": "pending"}]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="pending"):
        continue_after_human(tmp_path, "2026-07-05")
