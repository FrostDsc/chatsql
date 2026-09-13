# ChatSQL

Agentic Text-to-SQL：用自然语言查询 SQLite 数据库，基于 BIRD mini_dev 基准。

> 项目处于早期阶段（阶段 1：最小可用链路），README 将随开发迭代完善。

## 快速开始

```bash
uv sync
uv run python scripts/download_data.py   # 下载 BIRD mini_dev（约百 MB）
cp .env.example .env                     # 填入你的 OpenAI 兼容 API key
uv run python cli.py --db california_schools "How many schools have free meal rate above 50%?"
```

未配置 API key 时自动进入 mock 模式，可用于离线开发。

## 数据来源

[BIRD Mini-Dev](https://github.com/bird-bench/mini_dev)：500 条高质量 text-to-SQL 问答对，覆盖 11 个 SQLite 数据库。
