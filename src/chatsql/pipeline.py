"""最小可用链路：schema 摘要 → prompt → LLM 生成 SQL → 校验执行 → 答案。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from chatsql.db.executor import QueryResult, execute_readonly
from chatsql.db.schema import extract_schema, format_schema_for_prompt
from chatsql.llm.base import LLMClient

SYSTEM_PROMPT = """你是一名 SQLite 数据分析专家。根据给定的数据库 schema，把用户的自然语言问题转换成一条准确的 SQL 查询。

要求：
1. 只输出一条 SELECT 查询，包在 ```sql 代码块中，不要输出其他语句。
2. 使用 SQLite 方言，注意日期函数用 strftime/julianday。
3. 优先参考列的示例值来理解数据格式。
4. 除非用户明确说明，否则不要假设 schema 之外的表或列。"""

USER_TEMPLATE = """数据库 schema：
{schema}

问题：{question}"""

_SQL_BLOCK = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_sql(text: str) -> str:
    """从模型回复中提取 SQL：优先 ```sql 代码块，否则取全文。"""
    match = _SQL_BLOCK.search(text)
    sql = match.group(1) if match else text
    return sql.strip().rstrip(";")


@dataclass
class PipelineResult:
    question: str
    sql: str
    raw_response: str
    query_result: QueryResult | None = field(default=None)
    error: str | None = field(default=None)

    @property
    def ok(self) -> bool:
        return self.error is None and self.query_result is not None


def run_question(
    llm: LLMClient,
    db_path: str | Path,
    question: str,
    exec_timeout: int = 30,
    max_rows: int = 100,
) -> PipelineResult:
    tables = extract_schema(db_path)
    schema_text = format_schema_for_prompt(tables)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_TEMPLATE.format(schema=schema_text, question=question)},
    ]
    raw = llm.chat(messages)
    sql = extract_sql(raw)

    try:
        result = execute_readonly(db_path, sql, timeout_seconds=exec_timeout, max_rows=max_rows)
        return PipelineResult(question=question, sql=sql, raw_response=raw, query_result=result)
    except Exception as e:
        return PipelineResult(question=question, sql=sql, raw_response=raw, error=f"{type(e).__name__}: {e}")
