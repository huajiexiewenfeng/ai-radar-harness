from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".vendor"))
sys.path.insert(0, str(ROOT / "lib"))

from ai_radar.runner import run_live
from ai_radar.timeutil import run_date_for


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since-hours", type=int, default=48)
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--date")
    args = parser.parse_args()
    run_date = args.date or run_date_for()
    run = run_live(ROOT, run_date, args.since_hours, args.limit, filter_by_content_date=args.date is not None)
    print(f"AI Radar run {run['status']}: {run['item_count']} items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
