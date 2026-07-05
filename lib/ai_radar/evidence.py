from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_radar.urlutil import canonicalize_url


def merge_source_evidence(path: str | Path, source_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        data = json.loads(target.read_text(encoding="utf-8"))
    else:
        data = {"source_id": source_id, "records": []}
    merged: dict[str, dict[str, Any]] = {}
    for record in data.get("records", []):
        merged[canonicalize_url(record["url"])] = record
    for record in records:
        next_record = dict(record)
        next_record["url"] = canonicalize_url(next_record["url"])
        merged[next_record["url"]] = next_record
    result = {"source_id": source_id, "records": list(merged.values())}
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result
