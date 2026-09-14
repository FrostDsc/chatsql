"""Agent 状态机行为测试：纠错循环、校验拦截、降级、空结果软重试。

用脚本化 MockClient 精确控制每轮 LLM 输出，配合临时 SQLite 库。
"""
import sqlite3

import pytest

from chatsql.agent.graph import ask
from chatsql.config import ModelConfig, Settings
from chatsql.llm.openai_compat import MockClient


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


@pytest.fixture()
def settings(tmp_path):
    return Settings(
        model=ModelConfig(name="mock", base_url="", api_key=""),
        db_root=tmp_path,
        agent_max_rounds=3,
        retry_on_empty=True,
    )


def run(mock, settings, db_path, question="测试问题"):
    return ask(mock, settings, db_path, question, save_trace_to=None)


class TestSelfCorrection:
    def test_execution_error_triggers_retry(self, settings, db_path):
        mock = MockClient(responses=[
            "```sql\nSELECT * FROM nonexistent_table\n```",  # 校验能过，执行报错
            "```sql\nSELECT name FROM users ORDER BY id\n```",
            "按 id 排序是 alice、bob、carol。",
        ])
        state = run(mock, settings, db_path)

        assert state["status"] == "ok"
        assert state["attempts"] == 2
        assert len(state["error_history"]) == 1
        assert "nonexistent_table" in state["error_history"][0]["sql"]
        # 第二次生成应携带错误历史反馈
        second_gen_prompt = mock.calls[1][-1]["content"]
        assert "nonexistent_table" in second_gen_prompt
        assert "错误" in second_gen_prompt

    def test_unsafe_sql_intercepted_then_retried(self, settings, db_path):
        mock = MockClient(responses=[
            "```sql\nDROP TABLE users\n```",                 # 校验节点直接拦截
            "```sql\nSELECT COUNT(*) AS c FROM users\n```",
            "共 3 个用户。",
        ])
        state = run(mock, settings, db_path)

        assert state["status"] == "ok"
        assert state["attempts"] == 2
        assert "DROP" in state["error_history"][0]["error"].upper() or "Drop" in state["error_history"][0]["error"]
        # DROP 从未真正执行
        conn = sqlite3.connect(db_path)
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 3
        conn.close()

    def test_max_rounds_then_decline(self, settings, db_path):
        mock = MockClient(responses=[
            "```sql\nSELECT * FROM nope1\n```",
            "```sql\nSELECT * FROM nope2\n```",
            "```sql\nSELECT * FROM nope3\n```",
        ])
        state = run(mock, settings, db_path)

        assert state["status"] == "declined"
        assert state["attempts"] == 3                      # 不多不少，没有死循环
        assert len(state["error_history"]) == 3
        assert "抱歉" in state["answer"]
        assert len(mock.calls) == 3                        # decline 节点不再调 LLM


class TestEmptyResultRetry:
    def test_empty_result_triggers_one_soft_retry(self, settings, db_path):
        mock = MockClient(responses=[
            "```sql\nSELECT name FROM users WHERE age > 999\n```",
            "```sql\nSELECT COUNT(*) AS c FROM users\n```",
            "共 3 人。",
        ])
        state = run(mock, settings, db_path)

        assert state["status"] == "ok"
        assert state["attempts"] == 2
        assert state["empty_retried"] is True
        # 第二次生成收到了空结果提示
        assert "0 行" in mock.calls[1][-1]["content"]

    def test_empty_result_accepted_after_retry_used(self, settings, db_path):
        """修正后仍为空：如实回答，不再重试。"""
        empty_sql = "```sql\nSELECT name FROM users WHERE age > 999\n```"
        mock = MockClient(responses=[empty_sql, empty_sql, "没有找到符合条件的记录。"])
        state = run(mock, settings, db_path)

        assert state["status"] == "ok"
        assert state["attempts"] == 2
        assert state["query_result"]["rows"] == []


class TestSchemaLinking:
    def test_small_schema_skips_linking(self, settings, db_path):
        mock = MockClient(responses=[
            "```sql\nSELECT COUNT(*) AS c FROM users\n```",
            "3 人。",
        ])
        state = run(mock, settings, db_path)

        link_events = [e for e in state["trace"] if e["node"] == "link_schema"]
        assert link_events and "skipped" in link_events[0]["summary"]


class TestClarification:
    def test_non_sql_response_becomes_answer(self, settings, db_path):
        """模型返回纯文本（如澄清/无法回答）时不进入纠错循环，直接作为回答。"""
        mock = MockClient(responses=["这个数据库没有存储专业信息，请换一个数据库提问。"])
        state = run(mock, settings, db_path, "每个专业多少人？")

        assert state["status"] == "ok"
        assert "专业" in state["answer"]
        assert len(mock.calls) == 1  # 没有无意义的重试
        assert not state.get("error_history")


class TestTrace:
    def test_trace_covers_full_path(self, settings, db_path):
        mock = MockClient(responses=[
            "```sql\nSELECT COUNT(*) AS c FROM users\n```",
            "3 人。",
        ])
        state = run(mock, settings, db_path)

        nodes = [e["node"] for e in state["trace"]]
        assert nodes == [
            "load_schema", "link_schema", "retrieve", "generate_sql",
            "validate_sql", "execute_sql", "generate_answer",
        ]
