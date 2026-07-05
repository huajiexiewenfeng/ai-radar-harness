from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".vendor"))
sys.path.insert(0, str(ROOT / "lib"))

from ai_radar.state import load_json_file, write_json_file
from ai_radar.timeutil import run_date_for


def main() -> int:
    parser = argparse.ArgumentParser(description="Accept AI Radar selection recommendations for a local dry run.")
    parser.add_argument("--date", default=run_date_for())
    args = parser.parse_args()

    path = ROOT / "review" / f"{args.date}-selection.json"
    selection = load_json_file(path, {})
    if not selection:
        print(f"selection not found: {path}", file=sys.stderr)
        return 1
    changed = 0
    for item in selection.get("items", []):
        if item.get("decision") == "pending":
            item["decision"] = item.get("suggested_decision", "ignore")
            item["note"] = item.get("note") or "accepted recommendation for end-to-end workflow verification"
            changed += 1
    selection["status"] = "accepted_recommendations"
    write_json_file(path, selection)
    print(f"Accepted {changed} recommendations: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
