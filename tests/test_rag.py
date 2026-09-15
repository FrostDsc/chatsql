"""RAG 测试：向量库检索、索引构建、Agent 集成（全部用 HashEmbedder，不下载模型）。"""
import json
import sqlite3

import pytest

from chatsql.agent.graph import ask
from chatsql.config import ModelConfig, RagConfig, Settings
from chatsql.llm.openai_compat import MockClient
from chatsql.rag.embedder import HashEmbedder
from chatsql.rag.indexer import build_docs_for_db, docs_from_qa
from chatsql.rag.retriever import Retriever
from chatsql.rag.store import Doc, VectorStore


@pytest.fixture()
def embedder():
    return HashEmbedder(dim=64)


class TestVectorStore:
    def _store(self, embedder):
        docs = [
            Doc(text="consumption year date", kind="example", question_id=1),
            Doc(text="completely unrelated topic", kind="knowledge", question_id=2),
            Doc(text="date format year month", kind="knowledge", question_id=3),
        ]
        return VectorStore.build(docs, embedder.encode([d.text for d in docs]))

    def test_search_orders_by_similarity(self, embedder):
        store = self._store(embedder)
        q = embedder.encode(["year date"])[0]
        hits = store.search(q, top_k=3)
        assert hits[0].text != "completely unrelated topic"

    def test_kinds_filter(self, embedder):
        store = self._store(embedder)
        q = embedder.encode(["year date"])[0]
        hits = store.search(q, top_k=3, kinds={"example"})
        assert all(d.kind == "example" for d in hits) and len(hits) == 1

    def test_exclude_question_ids(self, embedder):
        store = self._store(embedder)
        q = embedder.encode(["consumption year date"])[0]
        hits = store.search(q, top_k=3, exclude_question_ids={1})
        assert all(d.question_id != 1 for d in hits)

    def test_save_load_roundtrip(self, embedder, tmp_path):
        store = self._store(embedder)
        store.save(tmp_path, "t")
        loaded = VectorStore.load(tmp_path, "t")
        q = embedder.encode(["year date"])[0]
        assert [d.text for d in loaded.search(q, top_k=3)] == [d.text for d in store.search(q, top_k=3)]
        assert VectorStore.exists(tmp_path, "t")


class TestIndexer:
    def test_docs_from_qa(self, tmp_path):
        data = [
            {"question_id": 1, "db_id": "a", "question": "q1", "evidence": "e1", "SQL": "SELECT 1"},
            {"question_id": 2, "db_id": "a", "question": "q2", "evidence": "", "SQL": "SELECT 2"},
            {"question_id": 3, "db_id": "b", "question": "q3", "evidence": "e3", "SQL": "SELECT 3"},
        ]
        p = tmp_path / "mini.json"
        p.write_text(json.dumps(data))
        docs = docs_from_qa(p, "a")
        assert len(docs) == 3  # q1 example+knowledge, q2 example（evidence 为空不索引）
        assert {d.kind for d in docs} == {"example", "knowledge"}
        assert all(d.question_id in (1, 2) for d in docs)

    def test_column_docs(self, tmp_path):
        db_dir = tmp_path / "mydb"
        desc = db_dir / "database_description"
        desc.mkdir(parents=True)
        (desc / "users.csv").write_text(
            "original_column_name,column_name,column_description,data_format,value_description\n"
            "age,,age of user,integer,\n"
            "status,,,text,\"active means 在职\"\n",
            encoding="utf-8",
        )
        from chatsql.rag.indexer import docs_from_column_descriptions
        docs = docs_from_column_descriptions(desc)
        texts = [d.text for d in docs]
        assert any("users.age" in t and "age of user" in t for t in texts)
        assert any("users.status" in t and "在职" in t for t in texts)

    def _make_desc_db(self, tmp_path):
        db_dir = tmp_path / "mydb"
        desc = db_dir / "database_description"
        desc.mkdir(parents=True)
        (desc / "users.csv").write_text(
            "original_column_name,column_name,column_description,data_format,value_description\n"
            "age,,age of user,integer,\n",
            encoding="utf-8",
        )
        return tmp_path

    def test_build_docs_without_qa_json(self, tmp_path):
        """自定义数据库没有问答对文件：data_json=None 时只索引列描述。"""
        db_root = self._make_desc_db(tmp_path)
        docs = build_docs_for_db(db_root, None, "mydb")
        assert len(docs) == 1 and docs[0].kind == "column_doc"
        assert "users.age" in docs[0].text

    def test_build_docs_custom_qa_json(self, tmp_path):
        """自带问答对 JSON（BIRD 格式）时与列描述合并索引。"""
        db_root = self._make_desc_db(tmp_path)
        qa = tmp_path / "my_qa.json"
        qa.write_text(json.dumps([
            {"question_id": 1, "db_id": "mydb", "question": "最老的用户几岁？", "evidence": "", "SQL": "SELECT MAX(age) FROM users"},
        ]), encoding="utf-8")
        docs = build_docs_for_db(db_root, qa, "mydb")
        kinds = {d.kind for d in docs}
        assert kinds == {"example", "column_doc"}  # evidence 为空 → 无 knowledge


@pytest.fixture()
def rag_env(tmp_path, embedder):
    """临时 SQLite 库 + 对应的检索索引。"""
    db_path = tmp_path / "t.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO users VALUES (1, 'alice')")
    conn.commit()
    conn.close()

    index_dir = tmp_path / "index"
    docs = [
        Doc(text="Question: list all users\nSQL: SELECT name FROM users", kind="example", question_id=1),
        Doc(text="name column stores full names in lowercase", kind="knowledge", question_id=2),
    ]
    VectorStore.build(docs, embedder.encode([d.text for d in docs])).save(index_dir, "t")

    settings = Settings(
        model=ModelConfig(name="mock", base_url="", api_key=""),
        db_root=tmp_path,
        rag=RagConfig(enabled=True, index_dir=index_dir),
    )
    retriever = Retriever(index_dir, embedder)
    return settings, db_path, retriever


class TestAgentIntegration:
    def test_retrieved_content_enters_prompt(self, rag_env):
        settings, db_path, retriever = rag_env
        mock = MockClient(responses=["```sql\nSELECT name FROM users\n```", "alice。"])
        state = ask(mock, settings, db_path, "list all users please",
                    save_trace_to=None, retriever=retriever)

        assert state["status"] == "ok"
        prompt = mock.calls[0][-1]["content"]
        assert "相似问题的参考示例" in prompt
        assert "SELECT name FROM users" in prompt      # example 注入
        assert "full names in lowercase" in prompt     # knowledge 注入
        retrieve_events = [e for e in state["trace"] if e["node"] == "retrieve"]
        assert "命中" in retrieve_events[0]["summary"]

    def test_exclude_current_question(self, rag_env):
        settings, db_path, retriever = rag_env
        mock = MockClient(responses=["```sql\nSELECT 1\n```", "ok。"])
        state = ask(mock, settings, db_path, "list all users",
                    save_trace_to=None, retriever=retriever, exclude_question_ids=[1])
        # question_id=1 的 example 被排除，prompt 不含其 SQL
        assert "SELECT name FROM users" not in mock.calls[0][-1]["content"]
        assert state["retrieved_examples"] == []

    def test_rag_disabled_passthrough(self, rag_env):
        settings, db_path, retriever = rag_env
        disabled = Settings(**{**settings.__dict__, "rag": RagConfig(enabled=False)})
        mock = MockClient(responses=["```sql\nSELECT 1\n```", "ok。"])
        state = ask(mock, disabled, db_path, "anything", save_trace_to=None, retriever=retriever)
        prompt = mock.calls[0][-1]["content"]
        assert "相似问题的参考示例" not in prompt
        retrieve_events = [e for e in state["trace"] if e["node"] == "retrieve"]
        assert "skipped" in retrieve_events[0]["summary"]
