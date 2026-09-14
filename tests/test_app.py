"""Streamlit 界面无头冒烟测试（AppTest + mock 模式，不调真实 API）。"""
import os
from pathlib import Path

import pytest

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest  # noqa: E402

APP_PATH = str(Path(__file__).resolve().parents[1] / "app.py")


@pytest.fixture()
def at(monkeypatch):
    monkeypatch.setenv("CHATSQL_MOCK", "1")
    monkeypatch.setenv("CHATSQL_RAG", "0")  # 避免加载 embedding 模型
    os.environ.pop("OPENAI_API_KEY", None)  # 防止 .env 里的真实 key 使 mock 失效
    app = AppTest.from_file(APP_PATH, default_timeout=60)
    app.run()
    return app


def test_app_loads(at):
    assert not at.exception
    assert "ChatSQL" in at.title[0].value
    # 侧边栏库选择器列出 11 个 mini_dev 库
    assert len(at.sidebar.selectbox[0].options) == 11
    # mock 模式有提示条
    assert len(at.warning) >= 1


def test_ask_question_renders_card(at):
    at.chat_input[0].set_value("测试问题").run()
    assert not at.exception
    # 用户气泡 + 助手回答卡片
    assert len(at.chat_message) >= 2
    texts = [m.markdown[0].value for m in at.chat_message if m.markdown]
    assert any("测试问题" in t for t in texts)
