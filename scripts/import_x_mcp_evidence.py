from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".vendor"))
sys.path.insert(0, str(ROOT / "lib"))

from ai_radar.x_mcp_bridge import import_x_mcp_evidence


def main() -> int:
    parser = argparse.ArgumentParser(description="Import an X MCP get_users_posts payload into AI Radar evidence.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--payload-file", required=True)
    args = parser.parse_args()

    payload = json.loads(Path(args.payload_file).read_text(encoding="utf-8"))
    result = import_x_mcp_evidence(ROOT, args.date, args.source_id, payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
