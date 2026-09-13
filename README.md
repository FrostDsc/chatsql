# ChatSQL

Agentic Text-to-SQL：用自然语言查询 SQLite 数据库，基于 BIRD mini_dev 基准。

> 项目处于早期阶段（阶段 1：最小可用链路），README 将随开发迭代完善。

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
```

未配置 API key 时自动进入 mock 模式，可用于离线开发。

## 架构

LangGraph 状态机：`load_schema → link_schema（大库才裁剪）→ generate_sql → validate_sql（只读校验）→ execute_sql →（失败自纠错，最多 3 轮）→ generate_answer`。
每次问答的完整 trace 落盘到 `runs/*.jsonl`。

## 数据来源

[BIRD Mini-Dev](https://github.com/bird-bench/mini_dev)：500 条高质量 text-to-SQL 问答对，覆盖 11 个 SQLite 数据库。
