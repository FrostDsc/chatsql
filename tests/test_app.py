"""Streamlit 界面无头冒烟测试（AppTest + mock 模式 + 临时库，不调真实 API、不依赖数据目录）。"""
import os
import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest  # noqa: E402

APP_PATH = str(Path(__file__).resolve().parents[1] / "app.py")
FIXTURE_DBS = ["california_schools", "student_club"]


@pytest.fixture()
def at(monkeypatch, tmp_path):
    monkeypatch.setenv("CHATSQL_MOCK", "1")
    monkeypatch.setenv("CHATSQL_RAG", "0")  # 避免加载 embedding 模型
    monkeypatch.setenv("CHATSQL_DB_ROOT", str(tmp_path))  # 指向临时库目录，脱离真实数据
    os.environ.pop("OPENAI_API_KEY", None)  # 防止 .env 里的真实 key 使 mock 失效
    for db in FIXTURE_DBS:
        db_dir = tmp_path / db
        db_dir.mkdir()
        conn = sqlite3.connect(db_dir / f"{db}.sqlite")
        conn.executescript("CREATE TABLE t(a INTEGER); INSERT INTO t VALUES (1), (2);")
        conn.close()
    import streamlit as st
    st.cache_resource.clear()  # 清掉上一个测试缓存的 settings/llm，保证本测试的 db_root 生效
    st.cache_data.clear()      # schema 抽取结果缓存也要清
    app = AppTest.from_file(APP_PATH, default_timeout=60)
    app.run()
    return app


def test_app_loads(at):
    assert not at.exception
    assert "ChatSQL" in at.title[0].value
    # 侧边栏库选择器列出临时目录里的测试库
    assert list(at.sidebar.selectbox[0].options) == FIXTURE_DBS
    # mock 模式有提示条
    assert len(at.warning) >= 1


def test_ask_question_renders_card(at):
    at.chat_input[0].set_value("测试问题").run()
    assert not at.exception
    # 用户气泡 + 助手回答卡片
    assert len(at.chat_message) >= 2
    texts = [m.markdown[0].value for m in at.chat_message if m.markdown]
    assert any("测试问题" in t for t in texts)


def _schema_expanders(at):
    return [e for e in at.expander if "Schema" in e.label]


def test_schema_panel_renders(at):
    assert not at.exception
    # 外层 Schema 面板存在，标注库名和表数
    outer = _schema_expanders(at)
    assert len(outer) == 1 and "california_schools" in outer[0].label
    # fixture 库的表 t（列 a）渲染成了列信息表
    assert any("`t`" in e.label for e in at.expander)
    col_tables = [df.value for df in at.dataframe
                  if list(df.value.columns) == ["列名", "类型", "主键", "示例值"]]
    assert len(col_tables) == 1
    assert col_tables[0].iloc[0]["列名"] == "a"
    assert "1" in col_tables[0].iloc[0]["示例值"]


def test_schema_panel_toggle_off(at):
    # 侧边栏第二个 toggle 是"显示 Schema"，关掉后面板消失
    at.sidebar.toggle[1].set_value(False).run()
    assert not at.exception
    assert _schema_expanders(at) == []
