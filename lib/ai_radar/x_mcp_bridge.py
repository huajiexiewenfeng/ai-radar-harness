from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ai_radar.collectors import payload_from_x_mcp_tool_result, records_from_x_mcp_posts
from ai_radar.config import load_sources
from ai_radar.evidence import merge_source_evidence


def _username_from_source(source: dict[str, Any]) -> str:
    if source.get("username"):
        return str(source["username"])
    parsed = urlparse(str(source.get("url") or ""))
    parts = [part for part in parsed.path.split("/") if part]
    return parts[0] if parts else str(source.get("id") or "unknown")


def _find_source(root: Path, source_id: str) -> dict[str, Any]:
    for source in load_sources(root / "sources" / "sources.yaml"):
        if source["id"] == source_id:
            return source
    raise ValueError(f"unknown source_id {source_id}")


def import_x_mcp_evidence(root: str | Path, run_date: str, source_id: str, payload_value: Any) -> dict[str, Any]:
    root_path = Path(root)
    source = _find_source(root_path, source_id)
    payload = payload_from_x_mcp_tool_result(payload_value)
    records = records_from_x_mcp_posts(payload, source, _username_from_source(source))
    evidence_path = root_path / "evidence" / run_date / f"{source_id}.json"
    merge_source_evidence(evidence_path, source_id, records)
    return {
        "status": "ok",
        "date": run_date,
        "source_id": source_id,
        "records": len(records),
        "evidence": str(evidence_path),
    }
