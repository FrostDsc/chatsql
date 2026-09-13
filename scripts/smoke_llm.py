"""真实 LLM 冒烟：挑 mini_dev 中带 JOIN 的标注题，跑完整链路并与 gold SQL 比对结果。

判定方式与 BIRD Execution Accuracy 一致：预测 SQL 与 gold SQL 的执行结果集合相等即算对。
需要先在 .env 配置 API key。

用法：uv run python scripts/smoke_llm.py [--n 3]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from chatsql.config import load_settings  # noqa: E402
from chatsql.db.executor import execute_readonly  # noqa: E402
from chatsql.llm.factory import create_llm  # noqa: E402
from chatsql.pipeline import run_question  # noqa: E402

DATA_JSON = PROJECT_ROOT / "data" / "mini_dev_data" / "mini_dev_sqlite.json"
DB_ROOT = PROJECT_ROOT / "data" / "mini_dev_data" / "dev_databases"


def result_set(rows: list[tuple]) -> set:
    return {tuple(str(v) for v in row) for row in rows}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=3, help="抽样题数")
    args = parser.parse_args()

    settings = load_settings()
    if settings.use_mock:
        print("未检测到 API key，请先配置 .env")
        return 1
    llm = create_llm(settings)

    samples = json.loads(DATA_JSON.read_text(encoding="utf-8"))
    picked, seen_dbs = [], set()
    for s in samples:
        if "join" in s["SQL"].lower() and s["db_id"] not in seen_dbs:
            picked.append(s)
            seen_dbs.add(s["db_id"])
        if len(picked) == args.n:
            break

    passed = 0
    for i, sample in enumerate(picked, 1):
        db_id = sample["db_id"]
        db_path = DB_ROOT / db_id / f"{db_id}.sqlite"
        question, gold_sql = sample["question"], sample["SQL"]

        result = run_question(
            llm, db_path, question,
            exec_timeout=settings.exec_timeout, max_rows=10_000,
        )
        if not result.ok:
            print(f"[{i}] {db_id}  FAIL  生成/执行失败: {result.error}")
            continue

        gold_rows = execute_readonly(db_path, gold_sql, max_rows=10_000).rows
        match = result_set(result.query_result.rows) == result_set(gold_rows)
        passed += match
        print(f"[{i}] {db_id}  {'PASS' if match else 'FAIL(结果不一致)'}")
        print(f"    问题: {question[:90]}")
        print(f"    生成: {result.sql[:120]}")
        if not match:
            print(f"    gold: {gold_sql[:120]}")
            print(f"    预测 {len(result.query_result.rows)} 行 vs gold {len(gold_rows)} 行")

    print(f"\n{passed}/{len(picked)} 与 gold 执行结果一致")
    return 0 if passed == len(picked) else 1


if __name__ == "__main__":
    sys.exit(main())
