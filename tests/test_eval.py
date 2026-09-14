"""评测模块测试：指标计算、runner 端到端（MockClient + gold SQL）、断点续跑。"""
import json
import sqlite3

import pytest

from chatsql.config import ModelConfig, Settings
from chatsql.eval.metrics import breakdown, compare_result_sets, ex_accuracy, failure_categories
from chatsql.eval.runner import run_eval
from chatsql.llm.openai_compat import MockClient


class TestCompareResultSets:
    def test_order_insensitive(self):
        assert compare_result_sets([(1, "a"), (2, "b")], [(2, "b"), (1, "a")])

    def test_none_and_float_normalized(self):
        assert compare_result_sets([(None, 1.5)], [(None, 1.5)])
        assert not compare_result_sets([(None,)], [("NULL",)]) is False  # None 统一为 "NULL"

    def test_mismatch(self):
        assert not compare_result_sets([(1,)], [(2,)])
        assert not compare_result_sets([(1,)], [(1,), (2,)])


class TestMetrics:
    def test_ex_excludes_gold_errors(self):
        details = [
            {"ex_match": True},
            {"ex_match": False, "failure": "result_mismatch"},
            {"ex_match": False, "failure": "gold_exec_error"},
        ]
        assert ex_accuracy(details) == 0.5  # 分母剔除 gold_exec_error

    def test_breakdown_and_failures(self):
        details = [
            {"ex_match": True, "difficulty": "simple", "db_id": "a"},
            {"ex_match": False, "failure": "declined", "difficulty": "hard", "db_id": "a"},
        ]
        bd = breakdown(details, "difficulty")
        assert bd["simple"]["ex"] == 1.0 and bd["hard"]["ex"] == 0.0
        assert failure_categories(details) == {"declined": 1}


@pytest.fixture()
def eval_env(tmp_path):
    """一个临时库 + 三条题目的迷你数据集。"""
    db_dir = tmp_path / "dev_databases" / "mydb"
    db_dir.mkdir(parents=True)
    conn = sqlite3.connect(db_dir / "mydb.sqlite")
    conn.execute("CREATE TABLE t (a INTEGER, b TEXT)")
    conn.executemany("INSERT INTO t VALUES (?, ?)", [(1, "x"), (2, "y")])
    conn.commit()
    conn.close()

    data = [
        {"question_id": 1, "db_id": "mydb", "difficulty": "simple",
         "question": "q1", "evidence": "", "SQL": "SELECT a FROM t"},
        {"question_id": 2, "db_id": "mydb", "difficulty": "simple",
         "question": "q2", "evidence": "", "SQL": "SELECT a FROM t"},
        {"question_id": 3, "db_id": "mydb", "difficulty": "simple",
         "question": "q3", "evidence": "", "SQL": "SELECT a FROM missing_table"},
    ]
    data_json = tmp_path / "mini.json"
    data_json.write_text(json.dumps(data))

    settings = Settings(model=ModelConfig(name="mock", base_url="", api_key=""),
                        db_root=tmp_path / "dev_databases")
    return settings, data_json


def _read_details(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


class TestRunner:
    def test_direct_config_all_correct(self, eval_env, tmp_path):
        settings, data_json = eval_env
        mock = MockClient(canned_sql="SELECT a FROM t")
        out = run_eval("direct", mock, settings, data_json, tmp_path / "run1")
        details = _read_details(out)

        assert len(details) == 3
        assert sum(d["ex_match"] for d in details) == 2          # q1 q2 对
        q3 = next(d for d in details if d["question_id"] == 3)
        assert q3["failure"] == "gold_exec_error"                 # gold 引用不存在的表
        assert ex_accuracy(details) == 1.0

    def test_agent_config_skips_answer_llm_call(self, eval_env, tmp_path):
        settings, data_json = eval_env
        mock = MockClient(canned_sql="SELECT a FROM t")
        out = run_eval("agent", mock, settings, data_json, tmp_path / "run2")
        details = _read_details(out)

        assert sum(d["ex_match"] for d in details) == 2
        # with_answer=False + q3 的 gold 执行失败不进入预测：LLM 仅被调用 2 次（q1/q2 各一次生成）
        assert len(mock.calls) == 2

    def test_resume_skips_completed(self, eval_env, tmp_path, capsys):
        settings, data_json = eval_env
        mock = MockClient(canned_sql="SELECT a FROM t")
        out_dir = tmp_path / "run3"
        run_eval("direct", mock, settings, data_json, out_dir, limit=2)
        assert len(_read_details(out_dir / "details.jsonl")) == 2

        run_eval("direct", mock, settings, data_json, out_dir)  # 全量续跑
        details = _read_details(out_dir / "details.jsonl")
        assert len(details) == 3                                  # 只补跑了 q3
        assert "本次跑 1 题" in capsys.readouterr().out
