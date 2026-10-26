from __future__ import annotations

import json
from pathlib import Path

from ai_radar.publish_workflow import finalize_selection, run_review_stage, workflow_status
from ai_radar.workflow_harness import run_until_human


DAY = "2026-07-05"


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _items(root: Path, *ids: str) -> None:
    _write(root / "data" / DAY / "items.json", [
        {"id": item_id, "title": f"New {item_id}", "status": "candidate",
         "recommended_action": "wiki_only"}
        for item_id in ids
    ])


def _selection(root: Path) -> dict:
    return json.loads((root / "review" / f"{DAY}-selection.json").read_text(encoding="utf-8"))


def test_review_rerun_merges_decisions_notes_new_and_stale(tmp_path: Path):
    _items(tmp_path, "keep", "gone")
    run_review_stage(tmp_path, DAY)
    selection = _selection(tmp_path)
    selection["items"][0].update(decision="publish", note="Human rationale", title="Old title")
    selection["items"][1].update(decision="wiki_only", note="Retain missing item")
    gone = dict(selection["items"][1])
    _write(tmp_path / "review" / f"{DAY}-selection.json", selection)
    _items(tmp_path, "keep", "new")

    run_review_stage(tmp_path, DAY)

    merged = {item["item_id"]: item for item in _selection(tmp_path)["items"]}
    assert merged["keep"]["decision"] == "publish"
    assert merged["keep"]["note"] == "Human rationale"
    assert merged["keep"]["title"] == "New keep"
    assert merged["keep"]["suggested_decision"] == "wiki_only"
    assert merged["new"]["decision"] == "pending"
    assert merged["gone"] == {**gone, "stale": True}

    _items(tmp_path, "keep", "gone", "new")
    run_review_stage(tmp_path, DAY)
    returned = {item["item_id"]: item for item in _selection(tmp_path)["items"]}
    assert not returned["gone"].get("stale")
    assert returned["gone"]["note"] == "Retain missing item"


def test_explicit_reset_backs_up_original_and_starts_pending(tmp_path: Path):
    _items(tmp_path, "keep", "gone")
    run_review_stage(tmp_path, DAY)
    selection = _selection(tmp_path)
    selection["items"][0].update(decision="publish", note="Preserve in backup")
    target = tmp_path / "review" / f"{DAY}-selection.json"
    _write(target, selection)
    original = target.read_bytes()
    _items(tmp_path, "keep", "new")

    run_review_stage(tmp_path, DAY, reset=True)

    backups = list(target.parent.glob(f"{DAY}-selection.bak-*.json"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original
    assert len(backups[0].stem.rsplit("-", 1)[1]) == 14
    assert {item["item_id"] for item in _selection(tmp_path)["items"]} == {"keep", "new"}
    assert all(item["decision"] == "pending" and item["note"] == ""
               for item in _selection(tmp_path)["items"])


def test_stale_pending_does_not_block_status_or_finalize(tmp_path: Path):
    _write(tmp_path / "review" / f"{DAY}-review.json", {"items": []})
    _write(tmp_path / "review" / f"{DAY}-selection.json", {"items": [
        {"item_id": "current", "decision": "ignore"},
        {"item_id": "old_pending", "decision": "pending", "stale": True},
        {"item_id": "old_publish", "decision": "publish", "stale": True},
        {"item_id": "old_wiki", "decision": "wiki_only", "stale": True},
    ]})
    _items(tmp_path, "current")

    status = workflow_status(tmp_path, DAY)
    assert status["pending_decisions"] == 0
    assert status["status"] == "ready_to_finalize"
    result = finalize_selection(tmp_path, DAY)
    assert result["stale_selected"] == ["old_publish", "old_wiki"]
    assert result["published_count"] == 0
    assert result["memory_pending_count"] == 0


def test_finalize_reports_missing_selected_ids_even_without_stale_flag(tmp_path: Path):
    _write(tmp_path / "review" / f"{DAY}-selection.json", {"items": [
        {"item_id": "absent", "decision": "publish"},
    ]})
    _items(tmp_path)
    assert finalize_selection(tmp_path, DAY)["stale_selected"] == ["absent"]


def test_until_human_passes_reset_without_collecting(tmp_path: Path):
    _items(tmp_path, "keep")
    run_review_stage(tmp_path, DAY)
    selection = _selection(tmp_path)
    selection["items"][0].update(decision="ignore", note="Already reviewed")
    _write(tmp_path / "review" / f"{DAY}-selection.json", selection)

    run_until_human(tmp_path, DAY, 48, 30, collect=False)
    assert _selection(tmp_path)["items"][0]["decision"] == "ignore"
    run_until_human(tmp_path, DAY, 48, 30, collect=False, reset_selection=True)
    assert _selection(tmp_path)["items"][0]["decision"] == "pending"
    assert list((tmp_path / "review").glob(f"{DAY}-selection.bak-*.json"))
