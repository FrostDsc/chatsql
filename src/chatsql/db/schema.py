"""从 SQLite 数据库抽取 schema，格式化成供 prompt 使用的 DDL 摘要。"""
from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    type: str
    is_pk: bool
    samples: tuple[str, ...]


@dataclass(frozen=True)
class TableInfo:
    name: str
    ddl: str
    columns: list[ColumnInfo]
    foreign_keys: list[str]  # 例如 "from_id = other_table.id"


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _sample_values(conn: sqlite3.Connection, table: str, column: str, limit: int = 3) -> tuple[str, ...]:
    try:
        rows = conn.execute(
            f"SELECT DISTINCT {_quote_ident(column)} FROM {_quote_ident(table)} "
            f"WHERE {_quote_ident(column)} IS NOT NULL LIMIT ?",
            (limit,),
        ).fetchall()
    except sqlite3.Error:
        return ()
    values = []
    for (v,) in rows:
        s = str(v)
        values.append(s if len(s) <= 50 else s[:47] + "...")
    return tuple(values)


def extract_schema(db_path: str | Path, sample_rows: int = 3) -> list[TableInfo]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        result = []
        for table in tables:
            ddl_row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            ddl = ddl_row[0] if ddl_row and ddl_row[0] else f"CREATE TABLE {_quote_ident(table)} (...)"

            columns = []
            for cid, name, ctype, _notnull, _dflt, pk in conn.execute(
                f"PRAGMA table_info({_quote_ident(table)})"
            ):
                columns.append(
                    ColumnInfo(
                        name=name,
                        type=ctype or "",
                        is_pk=bool(pk),
                        samples=_sample_values(conn, table, name, sample_rows),
                    )
                )

            fks = []
            for row in conn.execute(f"PRAGMA foreign_key_list({_quote_ident(table)})"):
                # row: (id, seq, ref_table, from_col, to_col, ...)
                fks.append(f"{table}.{row[3]} = {row[2]}.{row[4]}")
            result.append(TableInfo(name=table, ddl=ddl, columns=columns, foreign_keys=fks))
        return result
    finally:
        conn.close()


def read_csv_rows(csv_path: Path) -> list[dict]:
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


def _is_name_repeat(desc: str, col: str) -> bool:
    """column_description 只是列名复读（BIRD CSV 的常见占位），视为无信息量。"""
    norm = lambda s: s.replace(" ", "").replace("_", "").lower()
    return norm(desc) == norm(col)


def load_column_descriptions(db_dir: str | Path) -> dict[str, dict[str, str]]:
    """读 <db_dir>/database_description/*.csv，返回 {表名: {列名: 描述}}。

    描述由 column_description 与 value_description 拼接；column_description 是列名复读时丢弃；
    最终无有效内容的列不出现。自定义数据库没有该目录时返回空表。
    """
    desc_dir = Path(db_dir) / "database_description"
    result: dict[str, dict[str, str]] = {}
    if not desc_dir.is_dir():
        return result
    for csv_path in sorted(desc_dir.glob("*.csv")):
        table = csv_path.stem
        for row in read_csv_rows(csv_path):
            col = (row.get("original_column_name") or "").strip()
            if not col:
                continue
            parts = []
            if (desc := (row.get("column_description") or "").strip()) and not _is_name_repeat(desc, col):
                parts.append(desc)
            if (value_desc := (row.get("value_description") or "").strip()):
                parts.append(f"值说明: {value_desc}")
            if parts:
                result.setdefault(table, {})[col] = "；".join(parts)
    return result


def format_schema_for_prompt(tables: list[TableInfo], with_samples: bool = True) -> str:
    """把 schema 渲染成 prompt 文本：DDL + 列示例值注释 + 外键关系。"""
    parts = []
    for t in tables:
        lines = [t.ddl.rstrip(";") + ";"]
        if with_samples:
            for c in t.columns:
                if c.samples:
                    samples = ", ".join(repr(s) for s in c.samples)
                    lines.append(f"-- {t.name}.{c.name} 示例值: {samples}")
        if t.foreign_keys:
            lines.append(f"-- 外键: {'; '.join(t.foreign_keys)}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)
