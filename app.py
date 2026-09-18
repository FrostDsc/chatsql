"""ChatSQL Web 界面（Streamlit）。

用法：uv run streamlit run app.py
"""
from __future__ import annotations

import streamlit as st

from chatsql.agent.graph import ask
from chatsql.config import load_settings
from chatsql.llm.factory import create_llm
from chatsql.viz import chart_frame, infer_chart


@st.cache_resource
def get_settings():
    return load_settings()


@st.cache_resource
def get_llm():
    return create_llm(get_settings())


@st.cache_resource
def get_retriever():
    from chatsql.agent.graph import _make_retriever
    return _make_retriever(get_settings())


@st.cache_data
def get_schema(db_path: str):
    """按库缓存 schema 抽取结果，避免每次 rerun 重查 sqlite。"""
    from chatsql.db.schema import extract_schema
    return extract_schema(db_path)


def list_databases() -> list[str]:
    settings = get_settings()
    return sorted(p.name for p in settings.db_root.iterdir()
                  if p.is_dir() and (p / f"{p.name}.sqlite").exists())


def render_schema_panel(db_path) -> None:
    """Schema 面板：每张表的列信息、示例值、外键、DDL。"""
    tables = get_schema(str(db_path))
    with st.expander(f"📊 Schema：{db_path.stem}（{len(tables)} 张表）", expanded=False):
        for t in tables:
            with st.expander(f"`{t.name}`（{len(t.columns)} 列）"):
                st.dataframe(
                    [{"列名": c.name, "类型": c.type, "主键": "✓" if c.is_pk else "",
                      "示例值": ", ".join(c.samples)} for c in t.columns],
                    width="stretch", hide_index=True,
                )
                if t.foreign_keys:
                    st.caption(f"外键：{'；'.join(t.foreign_keys)}")
                with st.expander("DDL"):
                    st.code(t.ddl, language="sql")


def render_trace(state) -> None:
    """侧边栏 trace 面板：逐步节点 + 耗时，重试轮次计数。"""
    trace = state.get("trace", [])
    attempts = state.get("attempts", 1)
    with st.sidebar.expander(f"🔍 Agent trace（{attempts} 次生成，{len(trace)} 步）", expanded=False):
        for e in trace:
            st.caption(f"`{e['node']}` · {e['duration_ms']}ms — {e['summary']}")


def render_result(state) -> None:
    """渲染一次问答的完整卡片。"""
    st.markdown(state.get("answer", ""))
    if state.get("sql_draft"):
        with st.expander("生成的 SQL"):
            st.code(state["sql_draft"], language="sql")
    qr = state.get("query_result")
    if qr and qr["rows"]:
        with st.expander(f"查询结果（{len(qr['rows'])} 行{'，已截断' if qr['truncated'] else ''}）", expanded=True):
            st.dataframe([dict(zip(qr["columns"], row)) for row in qr["rows"]])
        kind = infer_chart(qr["columns"], qr["rows"])
        if kind != "none":
            df = chart_frame(qr["columns"], qr["rows"])
            (st.line_chart if kind == "line" else st.bar_chart)(df)


def main() -> None:
    st.set_page_config(page_title="ChatSQL", page_icon="📊", layout="wide")
    st.title("📊 ChatSQL — 用自然语言查询数据库")

    settings = get_settings()
    db_ids = list_databases()
    if not db_ids:
        st.error("未找到数据库，请先运行 `uv run python scripts/download_data.py`")
        st.stop()

    with st.sidebar:
        st.header("设置")
        db_id = st.selectbox("数据库", db_ids)
        use_rag = st.toggle("RAG 检索增强", value=settings.rag.enabled)
        show_schema = st.toggle("显示 Schema", value=True)
        st.caption(f"模型：`{settings.model.name}`")
        st.caption(f"模式：`{'mock（无 API key）' if settings.use_mock else '在线'}`")

    if settings.use_mock:
        st.warning("未配置 API key，当前为 mock 演示模式（SQL 为预置值）", icon="⚠️")

    if show_schema:
        render_schema_panel(settings.db_root / db_id / f"{db_id}.sqlite")

    if "messages" not in st.session_state:
        st.session_state.messages = []       # 渲染用：{role, content/state}
    if "dialogue_history" not in st.session_state:
        st.session_state.dialogue_history = []  # 传给 LLM 的问答对

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if msg["role"] == "user":
                st.markdown(msg["content"])
            else:
                render_result(msg["state"])

    question = st.chat_input("问点什么，例如：每个专业有多少成员？")
    if not question:
        return

    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Agent 工作中…"):
            db_path = settings.db_root / db_id / f"{db_id}.sqlite"
            state = ask(
                get_llm(), settings, db_path, question,
                dialogue_history=st.session_state.dialogue_history,
                retriever=(get_retriever() if use_rag else None),
            )
        render_result(state)
    render_trace(state)

    st.session_state.messages.append({"role": "assistant", "state": state})
    st.session_state.dialogue_history.append({"role": "user", "content": question})
    st.session_state.dialogue_history.append({"role": "assistant", "content": state.get("answer", "")})


main()
