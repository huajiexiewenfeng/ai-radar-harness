from __future__ import annotations

import json
from pathlib import Path

from ai_radar.state import load_json_file
from ai_radar.x_mcp_bridge import import_x_mcp_evidence


def test_import_x_mcp_evidence_writes_records(tmp_path: Path):
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir()
    (sources_dir / "sources.yaml").write_text(
        """
sources:
  - id: andrewng_x
    type: person_x
    enabled: true
    fetch_method: x_mcp
    url: https://x.com/AndrewYNg
    username: AndrewYNg
""",
        encoding="utf-8",
    )
    payload = {
        "data": [
            {
                "id": "2071988145667928442",
                "created_at": "2026-06-30T16:04:04.000Z",
                "text": "short",
                "note_tweet": {"text": "full mcp text"},
                "public_metrics": {"like_count": 1},
            }
        ]
    }

    result = import_x_mcp_evidence(tmp_path, "2026-07-01", "andrewng_x", payload)

    evidence = load_json_file(tmp_path / "evidence" / "2026-07-01" / "andrewng_x.json", {})
    assert result["records"] == 1
    assert evidence["records"][0]["text"] == "full mcp text"
    assert evidence["records"][0]["raw"]["fetch_method"] == "x_mcp"
    assert evidence["records"][0]["content_date"] == "2026-07-01"


def test_import_x_mcp_evidence_accepts_tool_result_text(tmp_path: Path):
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir()
    (sources_dir / "sources.yaml").write_text(
        """
sources:
  - id: karpathy_x
    type: person_x
    enabled: true
    fetch_method: x_mcp
    url: https://x.com/karpathy
""",
        encoding="utf-8",
    )
    tool_result = [{"type": "text", "text": json.dumps({"data": [{"id": "1", "text": "hello"}]})}]

    result = import_x_mcp_evidence(tmp_path, "2026-07-01", "karpathy_x", tool_result)

    assert result["source_id"] == "karpathy_x"
    assert result["records"] == 1
