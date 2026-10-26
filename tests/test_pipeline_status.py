from __future__ import annotations

from datetime import date
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "pipeline_status.py"


@pytest.fixture
def status_module():
    spec = importlib.util.spec_from_file_location("pipeline_status", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(root: Path, relative: str, value: object) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value), encoding="utf-8")


def _repo(root: Path) -> None:
    (root / "sources").mkdir()
    (root / "sources" / "sources.yaml").write_text(
        "sources:\n"
        "  - id: example_x\n    type: person_x\n    enabled: true\n"
        "    fetch_method: x_mcp\n    max_items_per_fetch: 5\n"
        "    username: PRIVATE_ACCOUNT\n    token: PRIVATE_TOKEN\n"
        "  - id: disabled_x\n    enabled: false\n    fetch_method: x_mcp\n",
        encoding="utf-8",
    )
    records = [{"source_id": "example_x", "source_type": "person_x",
                "captured_at": "2026-07-04T01:10:00Z", "raw": {}}
               for _ in range(7)]
    records[0]["raw"]["referenced_tweets"] = [{"type": "replied_to"}]
    records[1]["raw"]["referenced_tweets"] = [{"type": "retweeted"}]
    records[2]["raw"]["referenced_tweets"] = [{"type": "replied_to"}, {"type": "retweeted"}]
    _write(root, "evidence/2026-07-04/source.json",
           {"source_id": "example_x", "x_mcp_import": {}, "records": records})
    _write(root, "evidence/2026-07-04/zero.json",
           {"source_id": "disabled_x", "x_mcp_import": {"status": "ok"}, "records": []})
    (root / "evidence/2026-07-04/empty.json").touch()
    _write(root, "harness/trace/2026-07-04-run.json", {
        "date_filter": {"mode": "content_date"}, "status": "partial", "x_status": "ok",
        "failed_sources": [{"token": "PRIVATE_FAILURE"}], "started_at": "2026-07-04T12:30:00+08:00"})
    _write(root, "harness/trace/2026-07-04-human-gate.json", {"harness_status": "human_gate_required"})
    _write(root, "review/2026-07-04-selection.json", {"items": [
        {"decision": "ignore"}, {"decision": "pending"}, {"decision": "pending", "stale": True}]})
    _write(root, "review/2026-07-04-workflow-result.json", {"published_count": 1})
    _write(root, "memory/pending/2026-07-04.json", {"items": []})
    (root / "reports").mkdir()
    (root / "reports/2026-07-04-ai-radar.md").write_text("report", encoding="utf-8")
    for name in ("canonical", "wechat", "zhihu", "csdn"):
        path = root / f"articles/2026-07-04/{name}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("finalize output", encoding="utf-8")
    (root / "articles/2026-07-04/manual.md").write_text("manual package", encoding="utf-8")
    _write(root, "articles/2026-07-04/publish/receipt.json", {
        "article_url": "https://example.com/article?token=PRIVATE_QUERY",
        "status": "submitted_for_review", "date": "2026-07-04",
        "account": "PRIVATE_ACCOUNT", "cookie": "PRIVATE_COOKIE", "proxy": "http://127.0.0.1:1234"})
    _write(root, "review/2026-07-05-selection.json", {"items": [{"decision": "pending"}]})
    _write(root, "review/2026-07-05-workflow-result.json", {"published_count": 0})
    _write(root, "articles/2026-07-05/notes.json", {})
    for blocked in (".vendor", ".tmp", ".browser-profile-secret"):
        _write(root, f"articles/2026-07-04/{blocked}/receipt.json", {"account": "FORBIDDEN_READ"})


def _snapshot(root: Path) -> dict:
    return {str(path.relative_to(root)): (path.stat().st_mtime_ns, path.read_bytes())
            for path in root.rglob("*") if path.is_file()}


def test_pipeline_status_outputs_fields_missing_dates_and_never_writes(status_module, tmp_path, capsys, monkeypatch):
    _repo(tmp_path)
    before = _snapshot(tmp_path)
    original_read = Path.read_text

    def guarded_read(path, *args, **kwargs):
        assert not any(part in {".vendor", ".tmp"} or part.startswith(".browser-profile") for part in path.parts)
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read)
    assert status_module.main(["--from", "2026-07-04", "--to", "2026-07-06", "--format", "json"], root=tmp_path) == 0
    output = capsys.readouterr().out
    report = json.loads(output)
    row = report["days"][0]
    assert row["evidence"] == {
        "exists": True, "file_count": 3, "nonempty_file_count": 2, "record_file_count": 1,
        "record_count": 7, "unreadable_files": 1, "captured_hours": ["2026-07-04 09"]}
    assert row["x"]["enabled_x_mcp_sources"] == 1
    assert row["x"]["x_mcp_import_files"] == 2
    assert row["x"]["record_count"] == 7
    assert row["x"]["over_limit_item_count"] == 2
    assert row["x"]["excluded_item_count"] == 3
    assert row["x"]["replied_to_count"] == row["x"]["retweeted_count"] == 2
    assert row["run"]["date_filter_mode"] == "content_date"
    assert row["run"]["failed_sources_count"] == 1
    assert row["coverage_hint"] == "同日较早运行的产物已被覆盖"
    assert row["report_exists"]
    assert row["gate"]["harness_status"] == "human_gate_required"
    assert (row["selection"]["decided"], row["selection"]["pending"], row["selection"]["stale"]) == (1, 1, 1)
    assert row["finalize"]["bundle_complete"]
    assert row["finalize"]["memory_pending_exists"]
    assert row["articles"] == {"exists": True, "file_count": 6, "finalize_files": 4, "manual_package_files": 2}
    assert report["receipts"] == [{"article_url": "https://example.com/article", "status": "submitted_for_review", "date": "2026-07-04"}]
    assert report["missing_dates"] == [{"date": "2026-07-05", "weekday": "星期日"}, {"date": "2026-07-06", "weekday": "星期一"}]
    day5 = next(entry for entry in report["inconsistencies"] if entry["date"] == "2026-07-05")
    assert "有 workflow-result，但 selection 全是 pending" in day5["issues"]
    assert "有文章目录，但当天没有 run" in day5["issues"]
    assert "PRIVATE_" not in output and "127.0.0.1" not in output
    status_module.main(["--from", "2026-07-04", "--to", "2026-07-06"], root=tmp_path)
    markdown = capsys.readouterr().out
    assert "缺失日期清单（2 天）" in markdown
    assert "星期日" in markdown and "不一致清单" in markdown
    assert "PRIVATE_" not in markdown
    assert _snapshot(tmp_path) == before


def test_defaults_use_earliest_evidence_and_shanghai_today(status_module, tmp_path, monkeypatch):
    _repo(tmp_path)
    monkeypatch.setattr(status_module, "today_shanghai", lambda: date(2026, 7, 6))
    report = status_module.build_status(tmp_path)
    assert (report["from"], report["to"], report["timezone"]) == ("2026-07-04", "2026-07-06", "Asia/Shanghai")


def test_missing_empty_and_empty_list_selection_are_distinct(status_module, tmp_path):
    path = tmp_path / "review/2026-07-04-selection.json"
    path.parent.mkdir()
    path.touch()
    _write(tmp_path, "review/2026-07-05-selection.json", {"items": []})
    report = status_module.build_status(tmp_path, "2026-07-03", "2026-07-05")
    assert [row["selection"]["state"] for row in report["days"]] == ["无文件", "空文件", "空清单"]
    assert report["summary"]["selection_files"] == 2
    assert report["summary"]["evidence_dates"] == 0


@pytest.mark.parametrize("url", ["http://127.0.0.1:7897/private", "https://10.0.0.1/secret", "http://service.internal/api", "https://user:secret@example.com/a"])
def test_receipts_do_not_expose_private_endpoints(status_module, tmp_path, url):
    _write(tmp_path, "articles/2026-07-04/receipt.json", {"article_url": url, "status": "published", "date": "2026-07-04"})
    report = status_module.build_status(tmp_path, "2026-07-04", "2026-07-04")
    assert report["receipts"][0]["article_url"] == "待验证"


def test_invalid_range_fails_without_writes(status_module, tmp_path, capsys):
    before = _snapshot(tmp_path)
    with pytest.raises(SystemExit) as error:
        status_module.main(["--from", "2026-07-06", "--to", "2026-07-04"], root=tmp_path)
    assert error.value.code == 2
    assert "--from" in capsys.readouterr().err
    assert _snapshot(tmp_path) == before
