# ChatSQL

Agentic Text-to-SQL：用自然语言查询 SQLite 数据库，基于 BIRD mini_dev 基准。

> 开发进度：阶段 5/6 已完成（Streamlit 界面 + 图表可视化），详见 git tags。

## 快速开始

```bash
uv sync
uv run python scripts/download_data.py   # 下载 BIRD mini_dev（约 800MB）
cp .env.example .env                     # 填入你的 OpenAI 兼容 API key

# 单问（Agent 闭环：生成 → 校验 → 执行 → 自纠错 → 回答）
uv run python cli.py --db california_schools "How many schools have free meal rate above 50%?"

# 多轮对话（支持追问）
uv run python cli.py --db student_club --chat

# 调试：打印每步 trace；--mode direct 使用无纠错的单发 baseline
uv run python cli.py --db student_club --verbose "What's Angela Sanders's major?"

# Web 界面（推荐演示用）：选库、对话、SQL/结果表/自动图表、侧边栏 trace
uv run streamlit run app.py
```

未配置 API key 时自动进入 mock 模式，可用于离线开发。

## 架构

LangGraph 状态机：`load_schema → link_schema（大库才裁剪）→ retrieve（RAG）→ generate_sql → validate_sql（只读校验）→ execute_sql →（失败自纠错，最多 3 轮）→ generate_answer`。
每次问答的完整 trace 落盘到 `runs/*.jsonl`。

## RAG 检索

```bash
uv run python scripts/build_index.py   # 构建索引（首次下载约 90MB embedding 模型）
```

- 索引三类文档：相似问答对（few-shot）、专家知识（evidence）、列描述（database_description）
- Embedding 用本地 `all-MiniLM-L6-v2`，向量库为 numpy 自实现（余弦相似度）
- 评测时支持按 `question_id` 留一排除，避免数据泄漏
- 消融开关：`--no-rag` 或 `CHATSQL_RAG=0`

## 评测（BIRD mini_dev，500 题，Execution Accuracy）

模型：`deepseek-chat`（temperature=0），2026-09-14。RAG 评测按 question_id 留一排除防泄漏。

| 配置 | EX | 较基线 |
|---|---|---|
| baseline（单发直出） | 43.2% | - |
| + 自纠错（3 轮） | 43.7% | +0.5pp |
| + 自纠错 + RAG | **54.1%** | **+10.9pp** |

参考：BIRD 官方 baseline 中 GPT-4 为 47.8%。

**消融分析**（完整报告见 `eval/reports/`）：

- **RAG 是主要提升来源**：challenging 难度 +13.8pp（20.8% → 34.6%），11 个库中 8 个提升
- **自纠错消除了全部执行错误**（124 → 0），但对语义错误无能为力——BIRD 的失败以语义错误为主

**阴性结果（一次被证伪的假设）**：消融中发现 european_football_2 回退 13.7pp，最初怀疑是"空结果软重试"过度修正。做了对照实验（关闭软重试重跑该库 51 题）：EX 37.3%，未回升——假设证伪。逐题归因发现 11 题回退中 9 题首次生成就已分叉（attempts=1），真正原因是 baseline 与 agent 的 prompt 措辞差异导致的**生成方差**，而非纠错机制。软重试保留为可配置开关（`--no-empty-retry`），runner 支持 `--db`/`--difficulty` 子集实验。

复现：

```bash
uv run python scripts/run_eval.py --config direct --tag full_direct
uv run python scripts/run_eval.py --config agent --tag full_agent
uv run python scripts/run_eval.py --config agent_rag --tag full_agent_rag
uv run python scripts/make_report.py full_direct full_agent full_agent_rag
```

## 数据来源

[BIRD Mini-Dev](https://github.com/bird-bench/mini_dev)：500 条高质量 text-to-SQL 问答对，覆盖 11 个 SQLite 数据库。
