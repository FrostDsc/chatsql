"""安全执行器：只读校验 + 超时 + 行数截断。"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

import sqlglot
from sqlglot import expressions as exp


class UnsafeSQLError(ValueError):
    pass


class ExecutionTimeoutError(RuntimeError):
    pass


_FORBIDDEN = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Alter,
    exp.Create,
    exp.TruncateTable,
    exp.Grant,
    exp.Revoke,
    exp.Commit,
    exp.Pragma,
    exp.Attach,
    exp.Detach,
)


def validate_readonly(sql: str) -> str:
    """校验 SQL 是单条只读 SELECT，返回原 SQL。不合法时抛 UnsafeSQLError。"""
    try:
        statements = [s for s in sqlglot.parse(sql, read="sqlite") if s is not None]
    except sqlglot.errors.ParseError as e:
        raise UnsafeSQLError(f"SQL 解析失败：{e}") from e

    if len(statements) != 1:
        raise UnsafeSQLError(f"只允许单条语句，检测到 {len(statements)} 条")

    stmt = statements[0]
    if isinstance(stmt, exp.Select) or (isinstance(stmt, exp.Subquery) and isinstance(stmt.this, exp.Select)):
        pass
    elif isinstance(stmt, exp.Union) or isinstance(stmt, exp.Intersect) or isinstance(stmt, exp.Except):
        pass
    else:
        raise UnsafeSQLError(f"只允许 SELECT 查询，检测到：{type(stmt).__name__}")

    for node in stmt.walk():
        if isinstance(node, _FORBIDDEN):
            raise UnsafeSQLError(f"检测到禁止的操作：{type(node).__name__}")
    return sql


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[tuple]
    truncated: bool = False
    error: str | None = field(default=None)

    def to_markdown(self, max_rows: int = 20) -> str:
        if self.error:
            return f"ERROR: {self.error}"
        if not self.rows:
            return "(空结果)"
        header = "| " + " | ".join(self.columns) + " |"
        sep = "|" + "---|" * len(self.columns)
        body = [
            "| " + " | ".join(str(v) for v in row) + " |" for row in self.rows[:max_rows]
        ]
        suffix = ["\n…（已截断）"] if self.truncated else []
        return "\n".join([header, sep, *body, *suffix])


def execute_readonly(
    db_path: str | Path,
    sql: str,
    timeout_seconds: int = 30,
    max_rows: int = 100,
) -> QueryResult:
    """以只读模式执行 SELECT，超时中断，结果按 max_rows 截断。"""
    validate_readonly(sql)

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    start = time.monotonic()

    def _watchdog():
        if time.monotonic() - start > timeout_seconds:
            return 1  # 非零：中断当前查询，抛 OperationalError
        return 0

    conn.set_progress_handler(_watchdog, 10_000)
    try:
        cursor = conn.execute(sql)
        columns = [d[0] for d in cursor.description or []]
        rows = cursor.fetchmany(max_rows + 1)
        truncated = len(rows) > max_rows
        return QueryResult(columns=columns, rows=rows[:max_rows], truncated=truncated)
    except sqlite3.OperationalError as e:
        if time.monotonic() - start > timeout_seconds:
            raise ExecutionTimeoutError(f"查询超过 {timeout_seconds}s 被中断") from e
        raise
    finally:
        conn.set_progress_handler(None, 0)
        conn.close()
