# SignalForge AI Radar Harness

本地优先的 AI 信息雷达 workflow harness。

SignalForge 用来采集 AI 圈信号，保留 evidence，去重评分，停在 Human Gate，然后生成文章草稿和知识沉淀候选。

它不是普通资讯聚合器，而是面向「每日学习 + 发文 + 知识沉淀」的本地工作流。

## 它解决什么问题

- 从 RSS、HTML 页面、X adapter、已有 evidence snapshot 中采集 AI 信息。
- 把每条记录规范化为带日期的 evidence。
- 去重、评分，并给出 `publish / wiki_only / ignore` 建议。
- 在 Human Gate 停住，等待人或其他 agent 确认。
- 生成文章草稿。
- 导出 memory candidates，后续可接入 llm-wiki / 知识库。
- 生成本地静态 dashboard。

## 当前开源目标

第一阶段只开源 **core CLI**：

- 本地 RSS / HTML 采集
- evidence snapshot 回放
- review 生成
- Human Gate 人工确认
- finalize 生成文章和 memory candidates

第一阶段暂不做：

- 托管后台
- 托管数据库
- MCP server
- 自动发布公众号 / 知乎 / CSDN
- 内置任何付费 API 凭据

MCP 当前采用 adapter / bridge 方式，不是独立 MCP server。

## 工作流

```text
Sources -> Evidence -> Items -> Review -> Human Gate -> Articles + Memory Candidates
```

Human Gate 是设计的一部分。系统应该在发布决策前停下来，等待人或其他 agent 明确标记每条候选。

## 目录结构

```text
ai-radar-harness/
  lib/ai_radar/          # 核心 Python 包
  scripts/               # CLI 风格入口脚本
  sources/               # 来源和关键词配置
  harness/               # 运行配置、状态、trace
  evidence/              # 按日期/来源保存原始 evidence
  data/                  # 按日期保存评分后的 items
  review/                # Human Gate review 和 selection 文件
  reports/               # 每日 Markdown 日报
  drafts/                # 选题草稿
  articles/              # 最终文章包
  memory/pending/        # 等待接入 llm-wiki 的记忆候选
  dashboard/             # 本地静态 dashboard
  tests/                 # pytest 测试
```

开源仓库不要提交私人运行数据：

- `.browser-profile/`
- 个人 `evidence/`、`data/`、`review/`、`reports/`、`articles/`、`memory/`
- API key / token
- 私人 sources 配置

可以保留少量脱敏 example fixtures。

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/huajiexiewenfeng/ai-radar-harness.git
cd ai-radar-harness
```

### 2. 创建 Python 环境

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 3. 配置来源

编辑：

```text
sources/sources.yaml
harness/run-config.yaml
sources/keywords.yaml
```

第一版建议先从 RSS 和 HTML 来源开始。X、MCP、API、browser adapter 都是可选增强。

### 4. 运行每日采集

```bash
python scripts/run_ai_radar.py --date 2026-07-05 --since-hours 48 --limit 30
```

设置 `--date` 时，系统会按真实 `content_date` 过滤，而不是只改报告文件名。

产物：

```text
evidence/YYYY-MM-DD/<source_id>.json
data/YYYY-MM-DD/items.json
reports/YYYY-MM-DD-ai-radar.md
drafts/YYYY-MM-DD-topics.md
dashboard/dashboard-data.js
```

### 5. 停在 Human Gate

```bash
python scripts/run_human_gated_workflow.py --date 2026-07-05 --stage until-human
```

这会生成：

```text
review/YYYY-MM-DD-review.md
review/YYYY-MM-DD-review.json
review/YYYY-MM-DD-selection.json
```

此时 workflow 会停住。

打开 `review/YYYY-MM-DD-selection.json`，把每条：

```json
{
  "item_id": "2026-07-05-abc123",
  "decision": "pending",
  "note": ""
}
```

改成：

```text
publish
wiki_only
ignore
```

含义：

- `publish`：进入文章生成。
- `wiki_only`：不发文，进入知识沉淀候选。
- `ignore`：忽略。

### 6. Finalize

当所有 `decision` 都不再是 `pending` 后：

```bash
python scripts/run_human_gated_workflow.py --date 2026-07-05 --stage continue-after-human
```

产物：

```text
articles/YYYY-MM-DD/canonical.md
articles/YYYY-MM-DD/wechat.md
articles/YYYY-MM-DD/zhihu.md
articles/YYYY-MM-DD/csdn.md
memory/pending/YYYY-MM-DD.json
```

## 单独运行 Review / Finalize

也可以分两步直接运行 publish workflow。

生成 review 和 selection：

```bash
python scripts/run_publish_workflow.py --date 2026-07-05 --stage review
```

编辑：

```text
review/YYYY-MM-DD-selection.json
```

然后 finalize：

```bash
python scripts/run_publish_workflow.py --date 2026-07-05 --stage finalize
```

如果还有 `pending`，finalize 会拒绝继续。这是故意设计的安全边界。

## Evidence Snapshot 回放

如果 evidence 已经存在，可以不重新抓取外部来源，直接回放。

Python API 示例：

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

适合：

- 历史报告
- 回归测试
- 从其他 agent 导入 evidence
- 离线生成 review

## X Adapter

X 来源支持三种策略：

```text
x_mcp -> x_api -> browser_x
```

### x_mcp

agent 侧调用 X MCP 后，可以把 payload 导入本地 evidence。X MCP 的 `client_id` / `sk` 配置在 MCP server 或 agent connector 层，不写进 `harness/run-config.yaml`。

推荐分层：

```text
Codex / Claude / Cursor 的 MCP 配置
  -> 读取 X_MCP_CLIENT_ID 和 X_MCP_CLIENT_SECRET
  -> 调用 X MCP server
  -> 导出 tool result JSON
ai-radar-harness
  -> 把 JSON 导入 evidence/YYYY-MM-DD/<source>.json
```

`.env.example` 里给了本地环境变量命名约定：

```bash
X_MCP_CLIENT_ID="..."
X_MCP_CLIENT_SECRET="..."
```

不要提交真实 MCP 密钥。真实值应该放在本地 shell、secret manager，或者 Codex / Claude / Cursor 这类 agent 自己的 MCP 配置里。

命令：

```bash
python scripts/import_x_mcp_evidence.py \
  --date 2026-07-01 \
  --source-id andrewng_x \
  --payload-file /path/to/x-mcp-payload.json
```

payload 应兼容 X API v2 `get_users_posts` 结构。

### x_api

直连 X API fallback 从环境变量读取 X API Bearer Token：

```bash
export X_API_BEARER_TOKEN="..."
```

PowerShell：

```powershell
$env:X_API_BEARER_TOKEN = "..."
```

这条直连 fallback 路线当前不读取 `client_id` / `client_secret`。除非后续加 OAuth 换 token 的 wrapper，否则 core CLI 需要的是已经可用的 Bearer Token。

### browser_x

使用本地浏览器 profile 和 Playwright。适合作为 fallback，但稳定性不如 MCP/API。

## 其他 Agent 如何接入

### Shell Agent

任何能执行 shell 的 agent 都可以调用：

```bash
python scripts/run_ai_radar.py --date 2026-07-05
python scripts/run_publish_workflow.py --date 2026-07-05 --stage review
python scripts/run_publish_workflow.py --date 2026-07-05 --stage finalize
```

### File Agent

任何 agent 都可以读写：

```text
review/YYYY-MM-DD-review.json
review/YYYY-MM-DD-selection.json
```

唯一必须写入的是把 `decision` 从 `pending` 改成：

```text
publish | wiki_only | ignore
```

### MCP Agent

当前 milestone 不提供 MCP server。未来推荐暴露这些 MCP tools：

```text
ai_radar_run
ai_radar_status
ai_radar_list_candidates
ai_radar_mark_item
ai_radar_finalize
ai_radar_import_evidence
```

## 配置说明

`sources/sources.yaml` 定义来源：

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

来源也可以设置预算和状态：

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

`status: probation` 表示观察期来源：可以采集和统计，但不进入日报和 Human Gate。

## 测试

```bash
pytest tests -q
```

当前本地测试：

```text
61 passed
```

## License

正式发布前请选择开源协议。MIT 或 Apache-2.0 都适合第一版。

## 项目名称

- 品牌名：**SignalForge**
- 仓库名：**ai-radar-harness**
- 完整标题：**SignalForge AI Radar Harness**
