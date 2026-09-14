"""LangGraph 状态图组装与对外入口。"""
from __future__ import annotations

from pathlib import Path

from langgraph.graph import END, StateGraph

from chatsql.agent.nodes import make_nodes
from chatsql.agent.state import AgentState
from chatsql.agent.trace import save_trace
from chatsql.config import Settings
from chatsql.llm.base import LLMClient, Message


def _route_after_validate(state: AgentState, max_rounds: int) -> str:
    if state.get("validation_passed", False):
        return "execute"
    return "retry" if state.get("attempts", 0) < max_rounds else "decline"


def _route_after_execute(state: AgentState, settings: Settings) -> str:
    if state.get("query_result") is None:  # execute 节点失败时会置 None
        return "retry" if state.get("attempts", 0) < settings.agent_max_rounds else "decline"

    qr = state["query_result"]
    if (
        settings.retry_on_empty
        and len(qr["rows"]) == 0
        and not state.get("empty_retried", False)
        and state.get("attempts", 0) < settings.agent_max_rounds
    ):
        return "empty_retry"
    return "answer"


def build_agent(llm: LLMClient, settings: Settings, retriever=None):
    nodes = make_nodes(llm, settings, retriever=retriever)
    g = StateGraph(AgentState)
    for name, fn in nodes.items():
        g.add_node(name, fn)

    g.set_entry_point("load_schema")
    g.add_edge("load_schema", "link_schema")
    g.add_edge("link_schema", "retrieve")
    g.add_edge("retrieve", "generate_sql")
    g.add_edge("generate_sql", "validate_sql")
    g.add_conditional_edges(
        "validate_sql",
        lambda s: _route_after_validate(s, settings.agent_max_rounds),
        {"execute": "execute_sql", "retry": "generate_sql", "decline": "decline"},
    )
    g.add_conditional_edges(
        "execute_sql",
        lambda s: _route_after_execute(s, settings),
        {
            "answer": "generate_answer",
            "retry": "generate_sql",
            "empty_retry": "mark_empty_retry",
            "decline": "decline",
        },
    )
    g.add_edge("mark_empty_retry", "generate_sql")
    g.add_edge("generate_answer", END)
    g.add_edge("decline", END)
    return g.compile()


_UNSET = object()


def _make_retriever(settings: Settings):
    """RAG 开启时构建检索器（懒加载 embedding 模型）；关闭时返回 None。"""
    if not settings.rag.enabled:
        return None
    from chatsql.rag.embedder import SentenceTransformerEmbedder
    from chatsql.rag.retriever import Retriever

    return Retriever(settings.rag.index_dir, SentenceTransformerEmbedder(settings.rag.embedding_model))


def ask(
    llm: LLMClient,
    settings: Settings,
    db_path: str | Path,
    question: str,
    dialogue_history: list[Message] | None = None,
    save_trace_to: Path | None | object = _UNSET,
    retriever=_UNSET,
    exclude_question_ids: list[int] | None = None,
) -> AgentState:
    """跑一轮完整 Agent 问答，返回最终状态（含 answer/status/trace）。

    save_trace_to 默认（不传）写入 settings.trace_dir；显式传 None 则关闭落盘。
    retriever 默认按 settings.rag 自动构建；显式传 None 则关闭检索（测试/消融用）。
    """
    if retriever is _UNSET:
        retriever = _make_retriever(settings)
    graph = build_agent(llm, settings, retriever=retriever)
    initial: AgentState = {
        "question": question,
        "db_path": str(db_path),
        "dialogue_history": dialogue_history or [],
        "exclude_question_ids": exclude_question_ids or [],
        "attempts": 0,
        "empty_retried": False,
        "error_history": [],
        "trace": [],
    }
    final = graph.invoke(initial)
    if save_trace_to is _UNSET:
        save_trace_to = settings.trace_dir
    if save_trace_to:
        save_trace(save_trace_to, final)  # type: ignore[arg-type]
    return final
