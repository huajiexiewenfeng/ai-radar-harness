from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_radar.state import load_json_file, write_json_file


def baseline_path(root: str | Path, source_id: str) -> Path:
    return Path(root) / "store" / "baselines" / f"{source_id}.json"


def load_baseline(root: str | Path, source_id: str) -> dict[str, Any]:
    path = baseline_path(root, source_id)
    return load_json_file(path, {"schema_version": 1, "source_id": source_id, "entries": {}})


def write_baseline(root: str | Path, baseline: dict[str, Any]) -> None:
    write_json_file(baseline_path(root, baseline["source_id"]), baseline)


def update_baseline_entry(root: str | Path, baseline: dict[str, Any], canonical_url: str, entry: dict[str, Any]) -> dict[str, Any]:
    next_baseline = dict(baseline)
    next_entries = dict(next_baseline.get("entries", {}))
    next_entries[canonical_url] = dict(entry)
    next_baseline["entries"] = next_entries
    write_baseline(root, next_baseline)
    return next_baseline


def stateful_versioned_url(canonical_url: str, metadata: dict[str, Any]) -> str:
    version = metadata.get("version")
    if version:
        suffix = str(version)
    else:
        suffix = str(metadata.get("content_hash") or "")[:8]
    return f"{canonical_url}#v={suffix}" if suffix else canonical_url
