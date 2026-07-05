from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_radar.publish_workflow import finalize_selection, run_review_stage, workflow_status
from ai_radar.runner import run_live
from ai_radar.state import write_json_file


def run_until_human(
    root: str | Path,
    run_date: str,
    since_hours: int,
    limit: int,
    *,
    collect: bool = True,
) -> dict[str, Any]:
    root = Path(root)
    collection = None
    if collect:
        collection = run_live(root, run_date, since_hours, limit, filter_by_content_date=True)
    review = run_review_stage(root, run_date)
    workflow = workflow_status(root, run_date)
    result = {
        "date": run_date,
        "harness_status": "human_gate_required",
        "collection": collection,
        "review": review,
        "workflow": workflow,
        "next_step": f"Edit {root / 'review' / f'{run_date}-selection.json'} then run continue-after-human.",
    }
    write_json_file(root / "harness" / "trace" / f"{run_date}-human-gate.json", result)
    return result


def continue_after_human(root: str | Path, run_date: str) -> dict[str, Any]:
    root = Path(root)
    workflow = workflow_status(root, run_date)
    if workflow.get("pending_decisions", 0) > 0:
        raise ValueError(f"selection has pending decisions: {workflow['pending_decisions']}")
    finalized = finalize_selection(root, run_date)
    next_workflow = workflow_status(root, run_date)
    result = {
        "date": run_date,
        "harness_status": "complete",
        "finalized": finalized,
        "workflow": next_workflow,
    }
    write_json_file(root / "harness" / "trace" / f"{run_date}-human-gate.json", result)
    return result
