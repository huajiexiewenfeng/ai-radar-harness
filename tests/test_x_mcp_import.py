from __future__ import annotations

import json
from pathlib import Path

from ai_radar.collectors import payload_from_x_mcp_tool_result


def test_payload_from_x_mcp_tool_result_accepts_tool_text_list():
    raw = [
        {
            "type": "text",
            "text": json.dumps({"data": [{"id": "1", "text": "hello"}], "meta": {"result_count": 1}}),
        }
    ]

    payload = payload_from_x_mcp_tool_result(raw)

    assert payload["data"][0]["id"] == "1"
    assert payload["meta"]["result_count"] == 1


def test_payload_from_x_mcp_tool_result_accepts_plain_payload(tmp_path: Path):
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps({"data": [{"id": "2", "text": "world"}]}), encoding="utf-8")

    payload = payload_from_x_mcp_tool_result(json.loads(payload_path.read_text(encoding="utf-8")))

    assert payload["data"][0]["id"] == "2"
