"""无 API key 时的冒烟验证：用 mini_dev 标注的 gold SQL 走通整条链路。

从 3 个不同数据库各取一条标注样本，把 gold SQL 塞进 MockClient，
验证 schema 抽取 → prompt → SQL 提取 → 安全执行 的完整通路。

用法：uv run python scripts/smoke_gold.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from chatsql.db.schema import extract_schema  # noqa: E402
from chatsql.llm.openai_compat import MockClient  # noqa: E402
from chatsql.pipeline import run_question  # noqa: E402

DATA_JSON = PROJECT_ROOT / "data" / "mini_dev_data" / "mini_dev_sqlite.json"
DB_ROOT = PROJECT_ROOT / "data" / "mini_dev_data" / "dev_databases"


def main() -> int:
    samples = json.loads(DATA_JSON.read_text(encoding="utf-8"))

    picked: dict[str, dict] = {}
    for s in samples:
        if s["db_id"] not in picked:
            picked[s["db_id"]] = s
        if len(picked) == 3:
            break

    failures = 0
    for db_id, sample in picked.items():
        db_path = DB_ROOT / db_id / f"{db_id}.sqlite"
        question, gold_sql = sample["question"], sample["SQL"]

        n_tables = len(extract_schema(db_path))
        result = run_question(MockClient(canned_sql=gold_sql), db_path, question)

        status = "OK " if result.ok else "FAIL"
        print(f"[{status}] {db_id}（{n_tables} 张表）")
        print(f"  问题: {question[:80]}")
        print(f"  SQL : {result.sql[:100]}")
        if result.ok:
            print(f"  结果: {len(result.query_result.rows)} 行 x {len(result.query_result.columns)} 列")
        else:
            print(f"  错误: {result.error}")
            failures += 1

    if failures:
        print(f"\n{failures}/3 失败")
        return 1
    print("\n3/3 通过：链路完整可用")
    return 0


if __name__ == "__main__":
    sys.exit(main())
