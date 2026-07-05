from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".vendor"))
sys.path.insert(0, str(ROOT / "lib"))

from ai_radar.publish_workflow import finalize_selection, run_review_stage
from ai_radar.timeutil import run_date_for


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AI Radar review, human selection, article, and memory workflow.")
    parser.add_argument("--date", default=run_date_for())
    parser.add_argument("--stage", choices=["review", "finalize"], default="review")
    args = parser.parse_args()

    if args.stage == "review":
        result = run_review_stage(ROOT, args.date)
    else:
        result = finalize_selection(ROOT, args.date)
    print(f"AI Radar publish workflow {result['status']}: {args.stage} {args.date}")
    for key in ("review", "selection", "memory_pending"):
        if result.get(key):
            print(f"- {key}: {result[key]}")
    article_paths = result.get("article_paths") or {}
    for name, path in article_paths.items():
        print(f"- article.{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
