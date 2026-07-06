---
name: ai-frontier-newsroom
description: Use this skill when the user wants to run or continue an AI frontier information workflow for news collection, evidence snapshots, human review, learning capture, and article drafting. Triggers include requests such as scan today, scan yesterday, run AI news, open the dashboard, continue after Human Gate, generate article drafts, or import X MCP evidence.
---

# AI Frontier Newsroom

## Purpose

Operate an AI frontier information workflow that turns public AI signals into reviewed learning and publishing material. Keep the skill as an entrypoint: call the repository CLI, preserve evidence, stop for human decisions, and summarize the next action.

## Locate The Project

Use the current working directory if it contains `scripts/run_human_gated_workflow.py`. Otherwise ask the user for the local `ai-radar-harness` path. Do not guess credentials or create new secret files.

Before running commands:

```powershell
$Root = Resolve-Path "."
Set-Location $Root
$env:PYTHONPATH = "$Root\.vendor;$Root\lib"
```

If `python` is unavailable, use the local Python executable provided by the user.

## Command Map

For "scan today", "run today", or Chinese equivalents such as "扫描今天" / "跑今天":

```powershell
python scripts/run_human_gated_workflow.py --stage until-human
```

For a specific report date:

```powershell
python scripts/run_human_gated_workflow.py --date YYYY-MM-DD --stage until-human
```

For a date range, run one date at a time and report each date's dashboard/review result:

```powershell
python scripts/run_human_gated_workflow.py --date YYYY-MM-DD --stage until-human
```

For "open dashboard" or "查看 dashboard", return the local file path:

```text
dashboard/index.html
```

For "continue after Human Gate", "继续生成文章", or "继续":

1. Inspect `review/YYYY-MM-DD-selection.json`.
2. Verify at least one item has `decision: publish` or `decision: wiki_only`.
3. Continue only after the user has confirmed the selection.

```powershell
python scripts/run_human_gated_workflow.py --date YYYY-MM-DD --stage continue-after-human
python scripts/run_publish_workflow.py --date YYYY-MM-DD --stage review
```

For "finalize article" or "生成最终稿":

```powershell
python scripts/run_publish_workflow.py --date YYYY-MM-DD --stage finalize
```

## Human Gate Rule

Default to stopping at Human Gate. Do not auto-generate final articles from newly collected material unless the user explicitly asks to continue after reviewing selections.

When reporting the Human Gate result, include:

- report date
- item count
- selection file path
- dashboard path
- current blocking action

## X Source Policy

Prefer the repository fallback order:

```text
x_mcp -> x_api -> browser_x
```

`client_id`, `client_secret`, `sk`, and bearer tokens belong in the agent/MCP/server environment, not in repository YAML. Never commit real credentials.

If the user provides an X MCP tool result, import it with:

```powershell
python scripts/import_x_mcp_evidence.py --date YYYY-MM-DD --source-id SOURCE_ID --payload-file PATH_TO_JSON
```

## Output Style

Respond in the user's language. For Chinese users, keep the summary concise and practical:

- "已跑到 Human Gate"
- "你需要确认哪些内容发布 / 沉淀 / 忽略"
- "Dashboard: ..."
- "Selection: ..."

Avoid explaining the whole harness unless the user asks.
