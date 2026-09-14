"""Agent 节点函数。通过 make_nodes(llm, settings) 闭包注入依赖，便于测试。"""
from __future__ import annotations

import time
from pathlib import Path

from chatsql.agent.prompts import (
    ANSWER_SYSTEM,
    ANSWER_USER,
    CORRECTION_APPENDIX,
    DECLINE_TEMPLATE,
    EMPTY_RESULT_HINT,
    EXAMPLES_SECTION,
    GENERATE_SYSTEM,
    GENERATE_USER,
    KNOWLEDGE_SECTION,
    LINKING_SYSTEM,
    LINKING_USER,
)
from chatsql.agent.state import AgentState
from chatsql.agent.trace import make_event
from chatsql.config import Settings
from chatsql.db.executor import QueryResult, UnsafeSQLError, execute_readonly, validate_readonly
from chatsql.db.schema import extract_schema, format_schema_for_prompt
from chatsql.llm.base import LLMClient
from chatsql.pipeline import extract_sql


def _format_error_history(history: list[dict]) -> str:
    parts = []
    for i, h in enumerate(history, 1):
        parts.append(f"第 {i} 次：\n```sql\n{h['sql']}\n```\n错误：{h['error']}")
    return "\n\n".join(parts)


def make_nodes(llm: LLMClient, settings: Settings, retriever=None):
    def load_schema(state: AgentState) -> dict:
        t0 = time.monotonic()
        tables = extract_schema(state["db_path"])
        return {
            "schema_text": format_schema_for_prompt(tables),
            "table_names": [t.name for t in tables],
            "_tables": tables,
            "trace": [make_event("load_schema", t0, f"加载 {len(tables)} 张表")],
        }

    def link_schema(state: AgentState) -> dict:
        t0 = time.monotonic()
        tables = state["_tables"]
        threshold = settings.linking_table_threshold
        if len(tables) <= threshold:
            return {
                "trace": [make_event(
                    "link_schema", t0,
                    f"skipped：{len(tables)} 张表 ≤ 阈值 {threshold}，使用全量 schema",
                )],
            }

        names_text = "\n".join(t.name for t in tables)
        raw = llm.chat([
            {"role": "system", "content": LINKING_SYSTEM},
            {"role": "user", "content": LINKING_USER.format(tables=names_text, question=state["question"])},
        ])
        selected = {line.strip().strip('"`').lower() for line in raw.splitlines() if line.strip()}
        chosen = [t for t in tables if t.name.lower() in selected]
        if not chosen:  # 模型输出无法匹配任何表名时回退全量，宁可多给不可漏给
            return {
                "trace": [make_event("link_schema", t0, "linking 结果为空，回退全量 schema")],
            }
        return {
            "schema_text": format_schema_for_prompt(chosen),
            "trace": [make_event(
                "link_schema", t0,
                f"裁剪：{len(tables)} → {len(chosen)} 张表 ({', '.join(t.name for t in chosen)})",
            )],
        }

    def retrieve(state: AgentState) -> dict:
        t0 = time.monotonic()
        if not settings.rag.enabled or retriever is None:
            return {
                "retrieved_examples": [],
                "retrieved_knowledge": [],
                "trace": [make_event("retrieve", t0, "skipped：RAG 未启用")],
            }
        db_id = Path(state["db_path"]).stem
        if not retriever.available(db_id):
            return {
                "retrieved_examples": [],
                "retrieved_knowledge": [],
                "trace": [make_event("retrieve", t0, f"skipped：{db_id} 无索引（先运行 scripts/build_index.py）")],
            }
        result = retriever.retrieve(
            db_id, state["question"],
            top_k_examples=settings.rag.top_k_examples,
            top_k_knowledge=settings.rag.top_k_knowledge,
            exclude_question_ids=set(state.get("exclude_question_ids", [])),
        )
        examples = [d.text for d in result.examples]
        knowledge = [d.text for d in result.knowledge]
        return {
            "retrieved_examples": examples,
            "retrieved_knowledge": knowledge,
            "trace": [make_event("retrieve", t0, f"命中 {len(examples)} 条示例、{len(knowledge)} 条知识")],
        }

    def generate_sql(state: AgentState) -> dict:
        t0 = time.monotonic()
        user = GENERATE_USER.format(schema=state["schema_text"], question=state["question"])

        examples = state.get("retrieved_examples") or []
        if examples:
            user += EXAMPLES_SECTION.format(
                examples="\n\n".join(f"---\n{e}" for e in examples)
            )
        knowledge = state.get("retrieved_knowledge") or []
        if knowledge:
            user += KNOWLEDGE_SECTION.format(
                knowledge="\n".join(f"- {k}" for k in knowledge)
            )

        history = state.get("error_history", [])
        if history:
            user += CORRECTION_APPENDIX.format(history=_format_error_history(history))
        elif state.get("empty_retried") and state.get("query_result") is not None:
            user += EMPTY_RESULT_HINT.format(sql=state["sql_draft"])

        messages = [{"role": "system", "content": GENERATE_SYSTEM}]
        messages += state.get("dialogue_history", [])
        messages.append({"role": "user", "content": user})

        raw = llm.chat(messages)
        sql = extract_sql(raw)
        attempts = state.get("attempts", 0) + 1
        return {
            "sql_draft": sql,
            "attempts": attempts,
            "trace": [make_event("generate_sql", t0, f"第 {attempts} 次生成：{sql[:80]}")],
        }

    def validate_sql(state: AgentState) -> dict:
        t0 = time.monotonic()
        sql = state["sql_draft"]
        try:
            validate_readonly(sql)
            return {"validation_passed": True, "trace": [make_event("validate_sql", t0, "通过")]}
        except UnsafeSQLError as e:
            return {
                "validation_passed": False,
                "error_history": [{"sql": sql, "error": str(e)}],
                "trace": [make_event("validate_sql", t0, f"拦截：{e}")],
            }

    def execute_sql(state: AgentState) -> dict:
        t0 = time.monotonic()
        sql = state["sql_draft"]
        try:
            result: QueryResult = execute_readonly(
                state["db_path"], sql,
                timeout_seconds=settings.exec_timeout, max_rows=settings.exec_max_rows,
            )
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            return {
                "query_result": None,
                "error_history": [{"sql": sql, "error": error}],
                "trace": [make_event("execute_sql", t0, f"执行失败：{error[:100]}")],
            }
        rows_n = len(result.rows)
        return {
            "query_result": {"columns": result.columns, "rows": result.rows, "truncated": result.truncated},
            "trace": [make_event("execute_sql", t0, f"成功，{rows_n} 行{'（截断）' if result.truncated else ''}")],
        }

    def mark_empty_retry(state: AgentState) -> dict:
        t0 = time.monotonic()
        return {
            "empty_retried": True,
            "trace": [make_event("mark_empty_retry", t0, "结果为空，触发一次修正重试")],
        }

    def generate_answer(state: AgentState) -> dict:
        t0 = time.monotonic()
        qr = state["query_result"]
        result = QueryResult(columns=qr["columns"], rows=qr["rows"], truncated=qr["truncated"])
        raw = llm.chat([
            {"role": "system", "content": ANSWER_SYSTEM},
            {"role": "user", "content": ANSWER_USER.format(
                question=state["question"], sql=state["sql_draft"],
                row_count=len(result.rows), truncated="，已截断" if result.truncated else "",
                result=result.to_markdown(),
            )},
        ])
        return {
            "answer": raw.strip(),
            "status": "ok",
            "trace": [make_event("generate_answer", t0, "已生成回答")],
        }

    def decline(state: AgentState) -> dict:
        t0 = time.monotonic()
        last = state["error_history"][-1] if state.get("error_history") else {"sql": state.get("sql_draft", ""), "error": "未知错误"}
        answer = DECLINE_TEMPLATE.format(
            attempts=state.get("attempts", 0), sql=last["sql"], error=last["error"],
        )
        return {
            "answer": answer,
            "status": "declined",
            "trace": [make_event("decline", t0, f"{state.get('attempts', 0)} 次尝试后放弃")],
        }

    return {
        "load_schema": load_schema,
        "link_schema": link_schema,
        "retrieve": retrieve,
        "generate_sql": generate_sql,
        "validate_sql": validate_sql,
        "execute_sql": execute_sql,
        "mark_empty_retry": mark_empty_retry,
        "generate_answer": generate_answer,
        "decline": decline,
    }
