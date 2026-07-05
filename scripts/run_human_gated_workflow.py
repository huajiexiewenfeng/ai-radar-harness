from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".vendor"))
sys.path.insert(0, str(ROOT / "lib"))

from ai_radar.timeutil import run_date_for
from ai_radar.workflow_harness import continue_after_human, run_until_human


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AI Radar as a human-gated harness.")
    parser.add_argument("--date", default=run_date_for())
    parser.add_argument("--since-hours", type=int, default=48)
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--stage", choices=["until-human", "continue-after-human"], default="until-human")
    parser.add_argument("--skip-collect", action="store_true", help="Use existing items.json and only rebuild review/selection.")
    args = parser.parse_args()

    try:
        if args.stage == "until-human":
            result = run_until_human(ROOT, args.date, args.since_hours, args.limit, collect=not args.skip_collect)
        else:
            result = continue_after_human(ROOT, args.date)
    except ValueError as exc:
        print(f"AI Radar human gate blocked: {exc}", file=sys.stderr)
        return 2

    print(f"AI Radar harness {result['harness_status']}: {args.date}")
    print(json.dumps(result.get("workflow", {}), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
