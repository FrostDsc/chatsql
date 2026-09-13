"""从 SQLite 数据库抽取 schema，格式化成供 prompt 使用的 DDL 摘要。"""
from __future__ import annotations

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
