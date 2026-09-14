"""从 mini_dev 数据构建单库检索文档集。

三类文档：
- example：其他题的 Question+SQL（few-shot 示例）
- knowledge：其他题的 evidence（专家标注的业务知识）
- column_doc：database_description CSV 的列描述（schema 文档，无泄漏问题）
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from chatsql.rag.store import Doc


def docs_from_qa(data_json: Path, db_id: str) -> list[Doc]:
    """从 mini_dev_sqlite.json 中取某个库的 example 和 knowledge 文档。"""
    samples = json.loads(data_json.read_text(encoding="utf-8"))
    docs: list[Doc] = []
    for s in samples:
        if s["db_id"] != db_id:
            continue
        qid = int(s["question_id"])
        docs.append(Doc(
            text=f"Question: {s['question']}\nSQL: {s['SQL']}",
            kind="example",
            question_id=qid,
        ))
        evidence = (s.get("evidence") or "").strip()
        if evidence:
            docs.append(Doc(text=evidence, kind="knowledge", question_id=qid))
    return docs


def _read_csv_rows(csv_path: Path) -> list[dict]:
    """BIRD 的 CSV 编码不统一（部分含 Windows-1252 字符），做降级解码。"""
    raw = csv_path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
    return list(csv.DictReader(text.splitlines()))


def docs_from_column_descriptions(desc_dir: Path) -> list[Doc]:
    """把 database_description/*.csv 的每行变成一条 column_doc。"""
    docs: list[Doc] = []
    if not desc_dir.is_dir():
        return docs
    for csv_path in sorted(desc_dir.glob("*.csv")):
        table = csv_path.stem
        for row in _read_csv_rows(csv_path):
                col = (row.get("original_column_name") or "").strip()
                if not col:
                    continue
                desc = (row.get("column_description") or "").strip()
                value_desc = (row.get("value_description") or "").strip()
                fmt = (row.get("data_format") or "").strip()
                parts = [f"{table}.{col}"]
                if fmt:
                    parts.append(f"({fmt})")
                if desc:
                    parts.append(f": {desc}")
                if value_desc:
                    parts.append(f"；值说明: {value_desc}")
                text = "".join(parts)
                if len(text) > len(f"{table}.{col}"):  # 至少有点描述才值得索引
                    docs.append(Doc(text=text, kind="column_doc"))
    return docs


def build_docs_for_db(db_root: Path, data_json: Path, db_id: str) -> list[Doc]:
    desc_dir = db_root / db_id / "database_description"
    return docs_from_qa(data_json, db_id) + docs_from_column_descriptions(desc_dir)
