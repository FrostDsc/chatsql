"""executor 安全校验与执行的单元测试（使用临时 SQLite 库）。"""
import sqlite3

import pytest

from chatsql.db.executor import (
    QueryResult,
    UnsafeSQLError,
    execute_readonly,
    validate_readonly,
)


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "t.sqlite"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, age INTEGER)")
    conn.executemany(
        "INSERT INTO users VALUES (?, ?, ?)",
        [(1, "alice", 30), (2, "bob", 25), (3, "carol", 35)],
    )
    conn.commit()
    conn.close()
    return path


class TestValidateReadonly:
    def test_plain_select_ok(self):
        assert validate_readonly("SELECT * FROM users")

    def test_cte_ok(self):
        assert validate_readonly("WITH t AS (SELECT 1 AS x) SELECT x FROM t")

    def test_union_ok(self):
        assert validate_readonly("SELECT 1 UNION SELECT 2")

    @pytest.mark.parametrize(
        "sql",
        [
            "INSERT INTO users VALUES (4, 'dave', 40)",
            "DROP TABLE users",
            "DELETE FROM users WHERE id = 1",
            "UPDATE users SET age = 0",
            "CREATE TABLE evil (x INT)",
            "SELECT 1; DROP TABLE users",
            "SELECT * FROM users; SELECT * FROM users",
            "ATTACH DATABASE 'x.db' AS x",
            "PRAGMA journal_mode=WAL",
        ],
    )
    def test_dangerous_rejected(self, sql):
        with pytest.raises(UnsafeSQLError):
            validate_readonly(sql)

    def test_unparseable_rejected(self):
        with pytest.raises(UnsafeSQLError):
            validate_readonly("SELEKT ??? FROM")


class TestExecuteReadonly:
    def test_select_returns_rows(self, db_path):
        result = execute_readonly(db_path, "SELECT name FROM users ORDER BY id")
        assert result.columns == ["name"]
        assert [r[0] for r in result.rows] == ["alice", "bob", "carol"]
        assert not result.truncated

    def test_max_rows_truncation(self, db_path):
        result = execute_readonly(db_path, "SELECT * FROM users", max_rows=2)
        assert len(result.rows) == 2
        assert result.truncated

    def test_write_blocked_by_validation(self, db_path):
        with pytest.raises(UnsafeSQLError):
            execute_readonly(db_path, "DELETE FROM users")

    def test_readonly_connection_blocks_writes(self, db_path):
        # 双保险：即使绕过校验，mode=ro 连接也无法写入
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO users VALUES (9, 'x', 1)")
        conn.close()

    def test_markdown_rendering(self):
        r = QueryResult(columns=["a", "b"], rows=[(1, "x"), (2, "y")])
        md = r.to_markdown()
        assert "| a | b |" in md and "alice" not in md
