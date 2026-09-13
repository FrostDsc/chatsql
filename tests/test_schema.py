"""schema 抽取的单元测试。"""
import sqlite3

import pytest

from chatsql.db.schema import extract_schema, format_schema_for_prompt


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "shop.sqlite"
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute(
        "CREATE TABLE orders ("
        "id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id), amount REAL)"
    )
    conn.execute("INSERT INTO customers VALUES (1, 'alice')")
    conn.execute("INSERT INTO customers VALUES (2, 'bob')")
    conn.execute("INSERT INTO orders VALUES (10, 1, 9.99)")
    conn.commit()
    conn.close()
    return path


def test_extract_tables_and_columns(db_path):
    tables = {t.name: t for t in extract_schema(db_path)}
    assert set(tables) == {"customers", "orders"}
    cols = {c.name for c in tables["orders"].columns}
    assert cols == {"id", "customer_id", "amount"}


def test_primary_key_detected(db_path):
    tables = {t.name: t for t in extract_schema(db_path)}
    pk_cols = [c.name for c in tables["customers"].columns if c.is_pk]
    assert pk_cols == ["id"]


def test_foreign_key_detected(db_path):
    tables = {t.name: t for t in extract_schema(db_path)}
    assert tables["orders"].foreign_keys == ["orders.customer_id = customers.id"]


def test_sample_values_in_prompt_text(db_path):
    text = format_schema_for_prompt(extract_schema(db_path))
    assert "CREATE TABLE customers" in text
    assert "'alice'" in text  # name 列示例值
    assert "orders.customer_id = customers.id" in text
