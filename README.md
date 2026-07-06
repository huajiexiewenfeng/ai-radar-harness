# SignalForge AI Radar Harness

A local-first AI signal workflow harness.

SignalForge collects AI signals from configured sources, keeps source evidence, deduplicates and scores items, stops at a Human Gate, then generates article drafts and memory candidates.

It is designed for people who want a daily AI research and publishing workflow, not another passive news feed.

## What It Does

- Collects AI signals from RSS, HTML pages, X adapters, and saved evidence snapshots.
- Normalizes each record into dated evidence.
- Deduplicates and scores items into publish / wiki-only / ignore recommendations.
- Stops at a Human Gate before article generation.
- Generates article drafts for long-form writing workflows.
- Exports memory candidates for a future llm-wiki / knowledge-base layer.
- Produces a static local dashboard.

## Project Status

This repository currently targets the **core CLI**:

- local RSS / HTML collection
- evidence snapshot replay
- review generation
- human selection
- finalize into articles and memory candidates

Not included in the first open-source milestone:

- hosted backend
- hosted database
- MCP server
- automatic publishing to WeChat / Zhihu / CSDN
- built-in paid API credentials

MCP support is currently an adapter/bridge pattern, not a standalone MCP server.

## Workflow

```text
Sources -> Evidence -> Items -> Review -> Human Gate -> Articles + Memory Candidates
```

The Human Gate is intentional. The harness should stop before publishing decisions and wait for a human or another agent to mark each candidate.

## Repository Layout

```text
ai-radar-harness/
  lib/ai_radar/          # Core Python package
  scripts/               # CLI-style entry scripts
  sources/               # Source and keyword configuration
  harness/               # Runtime config, state, and traces
  evidence/              # Raw collected evidence by date/source
  data/                  # Scored items by date
  review/                # Human Gate review and selection files
  reports/               # Daily Markdown reports
  drafts/                # Topic drafts
  articles/              # Final article bundles
  memory/pending/        # Memory candidates for future llm-wiki ingestion
  dashboard/             # Static local dashboard
  tests/                 # Pytest test suite
```

For a clean public repository, do not commit your private runtime data:

- `.browser-profile/`
- personal `evidence/`, `data/`, `review/`, `reports/`, `articles/`, `memory/`
- API keys or tokens
- private source lists

Keep example fixtures small and sanitized.

## Quick Start

### 1. Clone

```bash
git clone https://github.com/huajiexiewenfeng/ai-radar-harness.git
cd ai-radar-harness
```

### 2. Create a Python Environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 3. Configure Sources

Edit:

```text
sources/sources.yaml
harness/run-config.yaml
sources/keywords.yaml
```

The first public version should start with RSS and HTML sources. X, MCP, API, and browser adapters are optional.

### 4. Run a Daily Collection

```bash
python scripts/run_ai_radar.py --date 2026-07-05 --since-hours 48 --limit 30
```

When `--date` is set, the run filters by the real `content_date`, not merely the report filename.

Outputs:

```text
evidence/YYYY-MM-DD/<source_id>.json
data/YYYY-MM-DD/items.json
reports/YYYY-MM-DD-ai-radar.md
drafts/YYYY-MM-DD-topics.md
dashboard/dashboard-data.js
```

### 5. Stop at Human Gate

```bash
python scripts/run_human_gated_workflow.py --date 2026-07-05 --stage until-human
```

This creates:

```text
review/YYYY-MM-DD-review.md
review/YYYY-MM-DD-review.json
review/YYYY-MM-DD-selection.json
```

The workflow stops here.

Edit `review/YYYY-MM-DD-selection.json` and change each item:

```json
{
  "item_id": "2026-07-05-abc123",
  "decision": "pending",
  "note": ""
}
```

to one of:

```text
publish
wiki_only
ignore
```

### 6. Finalize

After all decisions are no longer `pending`:

```bash
python scripts/run_human_gated_workflow.py --date 2026-07-05 --stage continue-after-human
```

Outputs:

```text
articles/YYYY-MM-DD/canonical.md
articles/YYYY-MM-DD/wechat.md
articles/YYYY-MM-DD/zhihu.md
articles/YYYY-MM-DD/csdn.md
memory/pending/YYYY-MM-DD.json
```

## Run Review / Finalize Separately

You can run the publish workflow in two explicit stages:

```bash
python scripts/run_publish_workflow.py --date 2026-07-05 --stage review
```

Then edit:

```text
review/YYYY-MM-DD-selection.json
```

Finalize:

```bash
python scripts/run_publish_workflow.py --date 2026-07-05 --stage finalize
```

If any item is still `pending`, finalize fails by design.

## Evidence Snapshot Replay

If evidence already exists, you can replay it without collecting from live sources.

Python API example:

```python
from pathlib import Path
import json

from ai_radar.runner import run_from_evidence_snapshot

root = Path(".")
run_date = "2026-07-05"
records = []

for path in (root / "evidence" / run_date).glob("*.json"):
    payload = json.loads(path.read_text(encoding="utf-8"))
    records.extend(payload.get("records", []))

run = run_from_evidence_snapshot(
    root,
    run_date,
    records,
    limit=30,
    llm_config={"provider": "none", "max_llm_tokens_per_run": 200000},
    filter_content_date=True,
)

print(run["status"], run["item_count"])
```

This is useful for:

- historical reports
- regression testing
- importing evidence from another agent
- offline review generation

## X Adapters

The harness supports three X strategies:

```text
x_mcp -> x_api -> browser_x
```

### x_mcp

Agent-side MCP calls can import payloads into local evidence. X MCP credentials are configured in the MCP server or agent connector, not in `harness/run-config.yaml`.

Recommended split:

```text
Codex / Claude / Cursor MCP config
  -> reads X_MCP_CLIENT_ID and X_MCP_CLIENT_SECRET
  -> calls the X MCP server
  -> exports the tool result as JSON
ai-radar-harness
  -> imports that JSON into evidence/YYYY-MM-DD/<source>.json
```

Use `.env.example` as the local naming convention:

```bash
X_MCP_CLIENT_ID="..."
X_MCP_CLIENT_SECRET="..."
```

Do not commit real MCP credentials. Keep them in your local shell, secret manager, or agent-specific MCP configuration.

Use:

```bash
python scripts/import_x_mcp_evidence.py \
  --date 2026-07-01 \
  --source-id andrewng_x \
  --payload-file /path/to/x-mcp-payload.json
```

The payload should be compatible with X API v2 `get_users_posts`.

### x_api

Direct X API fallback uses an X API bearer token from the environment:

```bash
export X_API_BEARER_TOKEN="..."
```

PowerShell:

```powershell
$env:X_API_BEARER_TOKEN = "..."
```

`client_id` / `client_secret` are not used by this direct fallback path unless you build your own OAuth token minting wrapper. The current core CLI expects a ready-to-use bearer token.

### browser_x

Uses a local browser profile and Playwright. This is useful as a fallback, but it is less stable than MCP/API.

## Agent Integration

Other agents can integrate in four ways.

### Skill Agent

For chat-first use, install or copy:

```text
skills/ai-frontier-newsroom
```

Then trigger it from another agent chat:

```text
$ai-frontier-newsroom scan today
$ai-frontier-newsroom scan yesterday
$ai-frontier-newsroom continue after Human Gate
$ai-frontier-newsroom open dashboard
```

The skill is intentionally thin. It calls the CLI, stops at Human Gate by default, and reports the dashboard/review artifacts instead of hiding the workflow behind another service.

### Shell Agent

Any agent that can run shell commands can use:

```bash
python scripts/run_ai_radar.py --date 2026-07-05
python scripts/run_publish_workflow.py --date 2026-07-05 --stage review
python scripts/run_publish_workflow.py --date 2026-07-05 --stage finalize
```

### File Agent

Any agent can read and write:

```text
review/YYYY-MM-DD-review.json
review/YYYY-MM-DD-selection.json
```

The only required write is changing `decision` from `pending` to:

```text
publish | wiki_only | ignore
```

### MCP Agent

The current milestone does not ship an MCP server. The recommended future MCP tools are:

```text
ai_radar_run
ai_radar_status
ai_radar_list_candidates
ai_radar_mark_item
ai_radar_finalize
ai_radar_import_evidence
```

## Configuration Notes

`sources/sources.yaml` defines source behavior:

```yaml
sources:
  - id: openai_news
    type: company_blog
    enabled: true
    fetch_method: rss
    url: https://openai.com/news/
    feed_url: https://openai.com/news/rss.xml
    priority: high
    topics: [model_release, developer_tooling, research_release]
```

Each source can also use:

```yaml
dedupe_mode: link
status: active
source_budget:
  daily_fetch_limit: 20
  daily_candidate_limit: 5
  llm_candidate_limit: 2
  human_review_limit: 1
  max_text_chars: 4000
  noise_level: low
```

`status: probation` lets a source be observed without entering the daily report or Human Gate.

## Testing

```bash
pytest tests -q
```

Current local test suite:

```text
61 passed
```

## License

Choose an open-source license before publishing. MIT or Apache-2.0 are both reasonable defaults.

## Project Name

- Project brand: **SignalForge**
- Repository name: **ai-radar-harness**
- Full title: **SignalForge AI Radar Harness**
