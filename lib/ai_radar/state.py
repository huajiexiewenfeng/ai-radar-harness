from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json_file(path: str | Path, default: Any) -> Any:
    target = Path(path)
    if not target.exists():
        return default
    return json.loads(target.read_text(encoding="utf-8"))


def write_json_file(path: str | Path, data: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def urlhash_from_item_id(item_id: str) -> str:
    return item_id.rsplit("-", 1)[-1]


def merge_annotations(items: list[dict[str, Any]], annotations: dict[str, Any]) -> list[dict[str, Any]]:
    annotation_items = annotations.get("items", {})
    merged = []
    for item in items:
        next_item = dict(item)
        urlhash8 = urlhash_from_item_id(next_item["id"])
        annotation = annotation_items.get(urlhash8)
        if annotation:
            next_item["status"] = annotation.get("status", next_item.get("status", "candidate"))
            if annotation.get("note"):
                next_item["annotation_note"] = annotation["note"]
        merged.append(next_item)
    return merged
