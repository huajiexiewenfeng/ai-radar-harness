from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".vendor"))
sys.path.insert(0, str(ROOT / "lib"))

from ai_radar.health import evaluate_run_health
from ai_radar.timeutil import run_date_for


def main() -> int:
    parser = argparse.ArgumentParser(description="Check whether AI Radar daily outputs satisfy the user goals.")
    parser.add_argument("--date", default=run_date_for())
    parser.add_argument("--require-x", action="store_true", help="Treat unavailable X sources as a blocking failure.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    health = evaluate_run_health(ROOT, args.date, require_x=args.require_x)
    if args.json:
        print(json.dumps(health, ensure_ascii=False, indent=2))
    else:
        print(f"AI Radar health {health['status']} for {health['date']}")
        for name, goal in health["goals"].items():
            print(f"- {name}: {goal['status']} - {goal['detail']}")
        print(f"- x: {health['x']['status']} - {health['x']['detail']}")
    return 0 if health["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
