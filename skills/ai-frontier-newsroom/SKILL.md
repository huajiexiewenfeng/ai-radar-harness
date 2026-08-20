---
name: ai-frontier-newsroom
description: Use when the active project is AI Radar or ai-radar-harness and the task concerns its newsroom scan, Dashboard, Human Gate review, X evidence import, learning capture, or article pipeline; not for AI Research Observatory, the ai-observatory CLI, Coverage manifests, or observatory reports.
---

# AI Frontier Newsroom

## Purpose

Operate the user's personal AI frontier newsroom: collect AI signals, preserve evidence, summarize candidates, stop at Human Gate, then continue into article drafting or learning capture only after human confirmation.

This skill is an entrypoint. Do not reimplement the workflow. Call the local CLI under the AI Radar project and report the exact artifacts the user should inspect.

## Routing Boundary

Use this Skill only when the current repository, explicit project name, path, artifact, or command identifies AI Radar or AI Radar Harness.

- Radar markers: `ai-radar`, `ai-radar-harness`, `run_human_gated_workflow.py`, Newsroom Dashboard, publish selection, and the Radar article pipeline.
- Observatory markers: `ai-research-observatory`, `ai-observatory`, Evidence Ledger, Coverage manifests, and research-observation reports.

If Observatory markers identify the task, do not use this Skill; route to `ai-research-observatory`. A bare “继续” or “continue” is not a project marker. Resolve the active repository and the most recent explicit project context before choosing a Skill.

AI Radar may export Evidence to Observatory through a stable data contract. That integration does not transfer control between their workflows.

## Local Project

Use this project root by default:

```text
D:\ai-discovery\ai-radar
```

If that path is unavailable, fallback to:

```text
D:\ai-discovery\ai-radar-harness
```

Before running commands in PowerShell:

```powershell
$Root = "D:\ai-discovery\ai-radar"
if (-not (Test-Path -LiteralPath $Root)) { $Root = "D:\ai-discovery\ai-radar-harness" }
Set-Location $Root
$env:PYTHONPATH = "$Root\.vendor;$Root\lib"
$Python = "C:\Users\admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (-not (Test-Path -LiteralPath $Python)) { $Python = "python" }
```

## Command Map

For "扫描今天", "跑今天", "scan today", or "run today":

```powershell
& $Python scripts/run_human_gated_workflow.py --stage until-human
```

For "扫描昨天": compute yesterday in Asia/Shanghai and pass it as `--date YYYY-MM-DD`:

```powershell
& $Python scripts/run_human_gated_workflow.py --date YYYY-MM-DD --stage until-human
```

For a specific date:

```powershell
& $Python scripts/run_human_gated_workflow.py --date YYYY-MM-DD --stage until-human
```

For a date range, run one day at a time. Do not pretend the date range is a native single command unless the CLI supports it.

For "查看 dashboard" or "打开 dashboard", report this file:

```text
D:\ai-discovery\ai-radar\dashboard\index.html
```

If fallback root is used, report:

```text
D:\ai-discovery\ai-radar-harness\dashboard\index.html
```

For "继续生成文章" or "continue after Human Gate" when the active project is AI Radar:

A bare “继续” is accepted only after the active project has already been resolved as AI Radar and the user has confirmed the Radar selection.

1. Inspect `review/YYYY-MM-DD-selection.json`.
2. Verify the user has selected `publish`, `wiki_only`, or `ignore` decisions.
3. If all items are still `pending`, stop and ask the user to confirm in the dashboard/review file.
4. If selections exist, continue:

```powershell
& $Python scripts/run_human_gated_workflow.py --date YYYY-MM-DD --stage continue-after-human
& $Python scripts/run_publish_workflow.py --date YYYY-MM-DD --stage review
```

For "生成最终稿" or "finalize article":

```powershell
& $Python scripts/run_publish_workflow.py --date YYYY-MM-DD --stage finalize
```

## Human Gate Rule

Default to stopping at Human Gate. The workflow must not auto-generate final articles immediately after scanning.

After a scan, report only the useful decision artifacts:

- report date
- total candidate count
- publish/wiki/ignore/pending counts if available
- dashboard path
- selection file path
- next action: ask the user to confirm publish / wiki_only / ignore

## X Source Policy

When an AI Radar task reports an X MCP failure, browser login prompt, empty X result, or repeated X connection problem, recall AGC before starting a fresh diagnosis: call `agc.read` with `overview`, then search the exact query `X MCP` within `codex_workflow` / `project:ai-radar`, and apply the confirmed runbook `ai-radar-x-mcp-host-bridge-runbook` when present. Live tool evidence still outranks memory.

Use the configured fallback order:

```text
x_mcp -> x_api -> browser_x
```

For every interactive or scheduled scan, inspect `sources/sources.yaml` before running the local CLI. When enabled sources use `fetch_method: x_mcp`:

1. Resolve the host tool by its current normalized name `mcp__xapi_oauth__get_users_posts`. Use `mcp__xapi_oauth__get_users_me` once as the authentication preflight. Before declaring X MCP unavailable, inspect the tool registry for names containing both `xapi_oauth` and `get_users_posts`; a failed natural-language search for "X MCP" is not proof that the connector is missing.
2. If `get_users_me` succeeds, call `mcp__xapi_oauth__get_users_posts` only for enabled `x_mcp` sources. Never call sources with `enabled: false`. The local runner message `x_mcp is not injected into local Python runner` is expected: Python cannot invoke host MCP directly, so it is not a connection failure.
3. Treat each source's `max_items_per_fetch` and `exclude` fields as cost controls, not optional hints. Pass the configured item limit to `max_results`, use the configured `exclude` values, and request `id,text,created_at,referenced_tweets,public_metrics,entities,note_tweet` when supported. Do not silently fall back to a generic 20-item request.
4. The default daily X profile is intentionally small: at most 5 posts per enabled account, original posts and substantive quote posts only. If the MCP tool cannot filter post types server-side, still request no more than the configured limit; the importer will apply `exclude` before evidence is merged.
5. Save each tool payload to a temporary JSON file outside the repository. Save and import successful zero-result payloads too; they prove that the account was queried successfully for the requested window.
6. Import every successful payload before the local scan:

```powershell
& $Python scripts/import_x_mcp_evidence.py --date YYYY-MM-DD --source-id SOURCE_ID --payload-file PATH_TO_JSON
```

7. Run `run_human_gated_workflow.py --stage until-human` only after the imports complete. The runner consumes the merged date-scoped evidence.
8. Verify `x_source_diagnostics`, `x_method_counts`, X evidence record counts, and each evidence file's `x_mcp_import` marker. A source is healthy with zero posts only when `host_mcp_status: ok` confirms a successful query for that source and time window. Zero records without that marker remain unavailable. Also report when any enabled account exceeds its configured item limit or imported evidence still contains excluded reply/retweet records.
9. Once host X MCP succeeds, do not invoke bearer-token or browser fallbacks for the same source in that scan.

If the X MCP tool cannot be found after the registry check, or `get_users_me` fails, state the exact preflight failure. Continue with `x_api` only when `X_API_BEARER_TOKEN` is actually present; otherwise browser fallback is degraded evidence and must not be described as MCP/API coverage.

Do not place `client_id`, `sk`, `client_secret`, or bearer tokens in YAML or Markdown. Those belong in the local MCP server, agent connector, shell environment, or secret manager.

If the user provides an X MCP payload file, import it with:

```powershell
& $Python scripts/import_x_mcp_evidence.py --date YYYY-MM-DD --source-id SOURCE_ID --payload-file PATH_TO_JSON
```

## Article Publishing Rule

When newsroom work enters article drafting or platform adaptation, follow the `content-creator` skill for title/angle discussion, WeChat mobile publishing style, core visual prompts, and publishable HTML copy pages.

Keep newsroom-specific behavior limited to evidence collection, Human Gate decisions, article artifact paths, and source attribution. Do not duplicate detailed writing or WeChat formatting rules here.

## Output Style

Respond in Chinese by default for this user. Keep the result operational and short:

```text
已跑到 Human Gate。
Dashboard: ...
Selection: ...
待你确认：publish / wiki_only / ignore。
```

Avoid long harness explanations unless the user asks why something works that way.
