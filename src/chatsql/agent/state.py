"""Agent 状态定义。trace 和 error_history 用 append 语义（reducer），节点只需返回新增项。"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from chatsql.llm.base import Message


class SQLError(TypedDict):
    sql: str
    error: str


class TraceEvent(TypedDict):
    node: str
    duration_ms: int
    summary: str


class AgentState(TypedDict, total=False):
    # 输入
    question: str
    db_path: str
    dialogue_history: list[Message]  # 之前轮次的问答（user/assistant 交替）

    # 中间产物
    schema_text: str
    table_names: list[str]
    _tables: list[Any]                               # load_schema 缓存的 TableInfo，供 link_schema 用
    exclude_question_ids: list[int]                  # 评测时传当前题 id，检索留一排除
    retrieved_examples: list[str]                    # retrieve 节点命中的相似问答对
    retrieved_knowledge: list[str]                   # retrieve 节点命中的知识/列描述
    sql_draft: str                                     # 当前轮次生成的 SQL
    error_history: Annotated[list[SQLError], operator.add]
    attempts: int                                      # 已生成 SQL 的次数
    validation_passed: bool                            # validate_sql 节点写回
    empty_retried: bool                                # 空结果软重试是否已用过
    query_result: dict[str, Any]                       # {"columns", "rows", "truncated"}

    # 输出
    answer: str
    status: str                                        # "ok" | "declined"
    trace: Annotated[list[TraceEvent], operator.add]
