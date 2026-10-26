from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
from collections import Counter
from datetime import date, datetime, timedelta
import ipaddress
import json
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import yaml


ROOT = Path(__file__).resolve().parents[1]
SHANGHAI = ZoneInfo("Asia/Shanghai")
BUNDLE = ("canonical.md", "wechat.md", "zhihu.md", "csdn.md")
DECISIONS = {"publish", "wiki_only", "ignore"}
WEEKDAYS = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")
UNKNOWN = "待验证"
STATES = {"complete", "partial", "failed", "error", "ok", "unavailable", "not_configured",
          "disabled", "skipped", "blocked", "pending", "running", "not_started",
          "human_gate_required", "waiting_for_human", "selection_required", "ready_to_finalize",
          "submitted_for_review", "published", "draft", "rejected", "success"}


def _blocked(name: str) -> bool:
    return name in {".vendor", ".tmp"} or name.startswith(".browser-profile")


def _files(folder: Path, recursive: bool = False) -> list[Path]:
    if not folder.is_dir() or folder.is_symlink():
        return []
    result = []
    for current, dirs, names in os.walk(folder, followlinks=False):
        dirs[:] = sorted(name for name in dirs
                         if not _blocked(name) and not (Path(current) / name).is_symlink())
        result.extend(Path(current) / name for name in sorted(names)
                      if not _blocked(name) and not (Path(current) / name).is_symlink())
        if not recursive:
            break
    return sorted(result)


def _json(path: Path) -> tuple[object, str]:
    if path.is_symlink():
        return None, UNKNOWN
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return None, "无文件"
    except (OSError, UnicodeError):
        return None, UNKNOWN
    if not text.strip():
        return None, "空文件"
    try:
        return json.loads(text), "正常"
    except ValueError:
        return None, UNKNOWN


def _time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=SHANGHAI) if parsed.tzinfo is None else parsed.astimezone(SHANGHAI)
    except ValueError:
        return None


def _date(value: str) -> date:
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("expected YYYY-MM-DD")
    return parsed


def today_shanghai() -> date:
    return datetime.now(SHANGHAI).date()


def _date_dirs(folder: Path) -> list[date]:
    if not folder.is_dir():
        return []
    result = []
    for path in folder.iterdir():
        if not path.is_dir() or path.is_symlink() or _blocked(path.name):
            continue
        try:
            result.append(_date(path.name))
        except ValueError:
            pass
    return sorted(result)


def _sources(root: Path) -> tuple[dict, str]:
    try:
        data = yaml.safe_load((root / "sources" / "sources.yaml").read_text(encoding="utf-8-sig"))
        entries = data.get("sources", []) if isinstance(data, dict) else data
        if not isinstance(entries, list):
            return {}, UNKNOWN
        return {entry["id"]: entry for entry in entries if isinstance(entry, dict) and "id" in entry}, "正常"
    except (OSError, UnicodeError, yaml.YAMLError):
        return {}, UNKNOWN


def _public_url(value: object) -> str:
    if not isinstance(value, str):
        return UNKNOWN
    try:
        url = urlsplit(value)
        host = url.hostname or ""
        if url.scheme not in {"https", "http"} or url.username or url.password or "." not in host:
            return UNKNOWN
        if host.endswith((".local", ".localhost", ".internal", ".corp", ".lan", ".test", ".invalid")):
            return UNKNOWN
        try:
            if not ipaddress.ip_address(host).is_global:
                return UNKNOWN
        except ValueError:
            pass
        return urlunsplit((url.scheme, url.netloc, url.path, "", ""))
    except ValueError:
        return UNKNOWN


def _label(value: object, allowed: set[str] = STATES) -> str:
    return value if isinstance(value, str) and value in allowed else UNKNOWN


def _evidence(root: Path, day: str, sources: dict) -> tuple[dict, dict, list[datetime]]:
    paths = [path for path in _files(root / "evidence" / day) if path.suffix == ".json"]
    evidence = {"exists": (root / "evidence" / day).is_dir(), "file_count": len(paths),
                "nonempty_file_count": 0, "record_file_count": 0, "record_count": 0, "unreadable_files": 0}
    x = {"enabled_x_mcp_sources": sum(1 for source in sources.values()
                                       if source.get("enabled", True) and source.get("fetch_method") == "x_mcp"),
         "x_mcp_import_files": 0, "record_count": 0, "over_limit_item_count": 0,
         "unknown_limit_records": 0, "replied_to_count": 0, "retweeted_count": 0, "excluded_item_count": 0}
    captured = []
    x_counts = Counter()
    for path in paths:
        try:
            evidence["nonempty_file_count"] += int(path.stat().st_size > 0)
        except OSError:
            pass
        payload, state = _json(path)
        if state != "正常" or not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
            evidence["unreadable_files"] += 1
            continue
        marked = "x_mcp_import" in payload
        x["x_mcp_import_files"] += int(marked)
        records = payload["records"]
        evidence["record_file_count"] += int(bool(records))
        evidence["record_count"] += len(records)
        stamp = _time(payload.get("captured_at"))
        if stamp:
            captured.append(stamp)
        for record in records:
            if not isinstance(record, dict):
                continue
            stamp = _time(record.get("captured_at"))
            if stamp:
                captured.append(stamp)
            source_id = record.get("source_id") or payload.get("source_id")
            source = sources.get(source_id, {})
            raw = record.get("raw") if isinstance(record.get("raw"), dict) else {}
            is_x = marked or record.get("source_type") in {"person_x", "company_x"} or \
                source.get("type") in {"person_x", "company_x"} or \
                raw.get("fetch_method") in {"x_mcp", "x_api", "browser_x"}
            if not is_x:
                continue
            x["record_count"] += 1
            x_counts[source_id] += 1
            refs = record.get("referenced_tweets") or raw.get("referenced_tweets") or []
            kinds = {ref.get("type") for ref in refs if isinstance(ref, dict)} if isinstance(refs, list) else set()
            reply = "replied_to" in kinds or bool(record.get("replied_to") or raw.get("replied_to"))
            retweet = "retweeted" in kinds or bool(record.get("retweeted") or raw.get("retweeted"))
            x["replied_to_count"] += int(reply)
            x["retweeted_count"] += int(retweet)
            x["excluded_item_count"] += int(reply or retweet)
    for source_id, count in x_counts.items():
        limit = sources.get(source_id, {}).get("max_items_per_fetch")
        if isinstance(limit, int) and not isinstance(limit, bool) and limit >= 0:
            x["over_limit_item_count"] += max(0, count - limit)
        else:
            x["unknown_limit_records"] += count
    evidence["captured_hours"] = sorted({stamp.strftime("%Y-%m-%d %H") for stamp in captured})
    return evidence, x, captured


def _selection(path: Path) -> dict:
    payload, state = _json(path)
    entries = payload.get("items") if isinstance(payload, dict) else None
    if state == "正常" and not isinstance(entries, list):
        state = UNKNOWN
    entries = entries if isinstance(entries, list) else []
    if state == "正常" and not entries:
        state = "空清单"
    active = [entry for entry in entries if isinstance(entry, dict) and not entry.get("stale")]
    return {"state": state, "total": len(entries),
            "decided": sum(entry.get("decision") in DECISIONS for entry in active),
            "pending": sum(entry.get("decision") == "pending" for entry in active),
            "stale": sum(isinstance(entry, dict) and bool(entry.get("stale")) for entry in entries),
            "invalid": sum(entry.get("decision") not in DECISIONS | {"pending"} for entry in active)}


def _day(root: Path, day: str, sources: dict) -> tuple[dict, list[str]]:
    evidence, x, captured = _evidence(root, day, sources)
    run_data, run_state = _json(root / "harness" / "trace" / f"{day}-run.json")
    run_data = run_data if isinstance(run_data, dict) else {}
    started = _time(run_data.get("started_at"))
    failed = run_data.get("failed_sources")
    date_filter = run_data.get("date_filter") or {}
    run = {"state": run_state, "date_filter_mode": _label(date_filter.get("mode") if isinstance(date_filter, dict) else None,
            {"content_date", "captured_at", "captured_date", "time_window", "all", "none", "since_hours"}),
           "status": _label(run_data.get("status")), "x_status": _label(run_data.get("x_status")),
           "failed_sources_count": len(failed) if isinstance(failed, (list, dict)) else None,
           "started_at": started.isoformat() if started else None}
    coverage = "同日较早运行的产物已被覆盖" if started and any(stamp < started - timedelta(hours=1) for stamp in captured) else None
    gate, gate_state = _json(root / "harness" / "trace" / f"{day}-human-gate.json")
    selection = _selection(root / "review" / f"{day}-selection.json")
    article_dir = root / "articles" / day
    article_files = _files(article_dir, recursive=True)
    bundle = {name.removesuffix(".md"): (article_dir / name).is_file() and (article_dir / name).stat().st_size > 0
              for name in BUNDLE}
    finalize_files = sum(path.parent == article_dir and path.name in BUNDLE for path in article_files)
    result_path = root / "review" / f"{day}-workflow-result.json"
    result_data, result_state = _json(result_path)
    result_data = result_data if isinstance(result_data, dict) else {}
    memory_exists = (root / "memory" / "pending" / f"{day}.json").is_file()
    row = {"date": day, "evidence": evidence, "x": x, "run": run, "coverage_hint": coverage,
           "report_exists": (root / "reports" / f"{day}-ai-radar.md").is_file(),
           "gate": {"state": gate_state, "harness_status": _label(gate.get("harness_status")) if isinstance(gate, dict) else UNKNOWN},
           "selection": selection,
           "finalize": {"result_exists": result_path.is_file(), "result_state": result_state,
                        "bundle": bundle, "bundle_complete": all(bundle.values()), "memory_pending_exists": memory_exists},
           "articles": {"exists": article_dir.is_dir(), "file_count": len(article_files),
                        "finalize_files": finalize_files, "manual_package_files": len(article_files) - finalize_files}}
    issues = []
    active_count = selection["total"] - selection["stale"]
    if result_path.is_file() and active_count > 0 and selection["pending"] == active_count:
        issues.append("有 workflow-result，但 selection 全是 pending")
    elif result_path.is_file() and selection["pending"]:
        issues.append("有 workflow-result，但 selection 仍有 pending")
    if result_path.is_file() and selection["state"] in {"无文件", "空文件", UNKNOWN}:
        issues.append("有 workflow-result，但 selection 无有效证据")
    if article_dir.is_dir() and run_state == "无文件":
        issues.append("有文章目录，但当天没有 run")
    if result_data.get("published_count", 0) and not all(bundle.values()):
        issues.append("workflow-result 记录了文章生成，但四件套不齐")
    if result_path.is_file() and not memory_exists:
        issues.append("有 workflow-result，但无 memory/pending")
    if isinstance(gate, dict) and gate.get("harness_status") == "complete" and not result_path.is_file():
        issues.append("Gate 为 complete，但无 workflow-result")
    if evidence["unreadable_files"]:
        issues.append(f"evidence 有 {evidence['unreadable_files']} 个空文件或无法解析的文件，记录数待验证")
    if selection["invalid"]:
        issues.append("selection 含无效 decision")
    return row, issues


def build_status(root: Path, from_date: str | None = None, to_date: str | None = None) -> dict:
    root = Path(root)
    evidence_dates = _date_dirs(root / "evidence")
    end = _date(to_date) if to_date else today_shanghai()
    start = _date(from_date) if from_date else (evidence_dates[0] if evidence_dates else end)
    if start > end:
        raise ValueError("--from must not be later than --to")
    sources, source_state = _sources(root)
    days, missing, inconsistencies = [], [], []
    current = start
    while current <= end:
        row, issues = _day(root, current.isoformat(), sources)
        days.append(row)
        if not row["evidence"]["exists"]:
            missing.append({"date": current.isoformat(), "weekday": WEEKDAYS[current.weekday()]})
        if issues:
            inconsistencies.append({"date": current.isoformat(), "issues": issues})
        current += timedelta(days=1)
    receipts = []
    unreadable_receipts = 0
    for path in _files(root / "articles", recursive=True):
        if path.name != "receipt.json":
            continue
        receipt, state = _json(path)
        if not isinstance(receipt, dict) or state != "正常":
            unreadable_receipts += 1
            receipts.append({"article_url": UNKNOWN, "status": UNKNOWN, "date": UNKNOWN})
            continue
        try:
            receipt_date = _date(receipt.get("date", "")).isoformat()
        except (ValueError, TypeError):
            receipt_date = UNKNOWN
        receipts.append({"article_url": _public_url(receipt.get("article_url")),
                         "status": _label(receipt.get("status")), "date": receipt_date})
    return {"from": start.isoformat(), "to": end.isoformat(), "timezone": "Asia/Shanghai",
            "source_config_state": source_state, "days": days, "receipts": receipts,
            "missing_dates": missing, "inconsistencies": inconsistencies,
            "summary": {"evidence_dates": sum(row["evidence"]["exists"] for row in days),
                        "missing_evidence_dates": len(missing),
                        "selection_files": sum(row["selection"]["state"] != "无文件" for row in days),
                        "dates_with_decisions": [row["date"] for row in days if row["selection"]["decided"]],
                        "receipt_files": len(receipts), "unreadable_receipts": unreadable_receipts}}


def _hours(hours: list[str]) -> str:
    grouped: dict[str, list[str]] = {}
    for hour in hours:
        day, value = hour.split(" ")
        grouped.setdefault(day, []).append(value)
    return "; ".join(f"{day} {','.join(values)}时" for day, values in grouped.items()) or UNKNOWN


def render_markdown(report: dict) -> str:
    lines = [f"# AI Radar Pipeline Status: {report['from']} ~ {report['to']}", "",
             "时区 Asia/Shanghai。非空文件按字节数大于 0 计；记录数为 records 长度之和，不去重。",
             "X 来源数及上限使用当前 sources.yaml；超限为同来源当日记录数超过配置上限的条目数，不代表单次请求或费用。",
             "selection 的已决定/pending 不含 stale；写作包文件指 articles/D 中四件套以外的文件。finalize 不等于实际发布。", "",
             "| 日期 | evidence 文件/非空/记录；captured_at 小时 | X 启用/导入文件/记录/超限/回复或转发 | run mode/status/x_status/失败数；started_at | 覆盖提示 | 日报 | Gate | selection 已决定/pending/stale | finalize result/四件套/memory | articles 总/四件套/写作包 |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for row in report["days"]:
        e, x, run, sel, final, articles = (row[key] for key in ("evidence", "x", "run", "selection", "finalize", "articles"))
        evidence_cell = f"{e['file_count']}/{e['nonempty_file_count']}/{e['record_count']}; {_hours(e['captured_hours'])}" if e["exists"] else "无"
        if e["unreadable_files"]:
            evidence_cell += f"; {e['unreadable_files']} 文件待验证"
        xcell = f"{x['enabled_x_mcp_sources'] if report['source_config_state'] == '正常' else UNKNOWN}/{x['x_mcp_import_files']}/{x['record_count']}/{x['over_limit_item_count']}/{x['excluded_item_count']}"
        if x["unknown_limit_records"]:
            xcell += f"; {x['unknown_limit_records']} 条上限待验证"
        run_cell = f"{run['date_filter_mode']}/{run['status']}/{run['x_status']}/{run['failed_sources_count'] if run['failed_sources_count'] is not None else UNKNOWN}; {run['started_at'] or UNKNOWN}"
        if run["state"] != "正常":
            run_cell = "无" if run["state"] == "无文件" else UNKNOWN
        gate = row["gate"]
        gate_cell = "无" if gate["state"] == "无文件" else gate["harness_status"]
        selection_cell = f"{sel['decided']}/{sel['pending']}/{sel['stale']}" if sel["state"] == "正常" else sel["state"]
        final_cell = f"{'有' if final['result_exists'] else '无'}/{sum(final['bundle'].values())}/4/{'有' if final['memory_pending_exists'] else '无'}"
        lines.append(f"| {row['date']} | {evidence_cell} | {xcell} | {run_cell} | {row['coverage_hint'] or '无'} | {'有' if row['report_exists'] else '无'} | {gate_cell} | {selection_cell} | {final_cell} | {articles['file_count']}/{articles['finalize_files']}/{articles['manual_package_files']} |")
    summary = report["summary"]
    missing = "、".join(f"{entry['date']}（{entry['weekday']}）" for entry in report["missing_dates"]) or "无"
    issues = "; ".join(f"{entry['date']}: {'、'.join(entry['issues'])}" for entry in report["inconsistencies"]) or "无"
    lines += ["", f"缺失日期清单（{len(report['missing_dates'])} 天）：{missing}", "",
              f"不一致清单：{issues}", "",
              f"汇总：evidence 日期 {summary['evidence_dates']}；selection 文件 {summary['selection_files']}；有人工决定日期 {'、'.join(summary['dates_with_decisions']) or '无'}；receipt {summary['receipt_files']}。", "",
              "发布回执（扫描 articles 全目录，仅列回执证据）：", "",
              "| article_url | status | date |", "| --- | --- | --- |"]
    for receipt in report["receipts"]:
        lines.append(f"| {receipt['article_url']} | {receipt['status']} | {receipt['date']} |")
    if not report["receipts"]:
        lines.append("| 无 | 无 | 无 |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None, *, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description="Read-only AI Radar pipeline evidence audit.")
    parser.add_argument("--from", dest="from_date", metavar="YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", metavar="YYYY-MM-DD")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args(argv)
    try:
        report = build_status(root, args.from_date, args.to_date)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.format == "json" else render_markdown(report), end="\n" if args.format == "json" else "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
