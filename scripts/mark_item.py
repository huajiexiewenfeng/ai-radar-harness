from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".vendor"))
sys.path.insert(0, str(ROOT / "lib"))

from ai_radar.render import render_daily_report, render_dashboard_data, render_topic_draft
from ai_radar.runner import _recent_runs
from ai_radar.state import load_json_file, merge_annotations, urlhash_from_item_id, write_json_file
from ai_radar.timeutil import iso_now


VALID_STATUSES = {"candidate", "promote", "learn", "archive", "ignore", "unscored"}


def mark_item(root: Path, run_date: str, item_id: str, status: str, note: str = "") -> None:
    annotations_path = root / "harness" / "annotations.json"
    annotations = load_json_file(annotations_path, {"items": {}})
    key = urlhash_from_item_id(item_id)
    annotations.setdefault("items", {})[key] = {"status": status, "updated_at": iso_now(), "note": note}
    write_json_file(annotations_path, annotations)
    items_path = root / "data" / run_date / "items.json"
    if not items_path.exists():
        return
    items = merge_annotations(load_json_file(items_path, []), annotations)
    write_json_file(items_path, items)
    run = load_json_file(root / "harness" / "trace" / f"{run_date}-run.json", {})
    state = load_json_file(root / "harness" / "state.json", {})
    (root / "reports").mkdir(parents=True, exist_ok=True)
    (root / "reports" / f"{run_date}-ai-radar.md").write_text(render_daily_report(run_date, items, run), encoding="utf-8")
    (root / "drafts").mkdir(parents=True, exist_ok=True)
    (root / "drafts" / f"{run_date}-topics.md").write_text(render_topic_draft(run_date, items), encoding="utf-8")
    dashboard = render_dashboard_data(run_date, items, run, state, _recent_runs(root))
    (root / "dashboard").mkdir(parents=True, exist_ok=True)
    (root / "dashboard" / "dashboard-data.js").write_text(dashboard, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--status", required=True, choices=sorted(VALID_STATUSES))
    parser.add_argument("--note", default="")
    args = parser.parse_args()
    mark_item(ROOT, args.date, args.id, args.status, args.note)
    print(f"Marked {args.id} as {args.status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
