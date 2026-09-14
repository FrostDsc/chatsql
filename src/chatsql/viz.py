"""图表自动推断：根据查询结果的列结构决定是否画图、画什么图。

规则（宁缺毋滥）：
- 恰好 2 列、行数 2~30、第二列为数值 → 首列像日期/年份则折线图，否则柱状图
- 其余情况（0/1 行、单列、多列、超大结果）→ 不画
"""
from __future__ import annotations

import re
from typing import Any, Literal

ChartKind = Literal["bar", "line", "none"]

_DATE_LIKE = re.compile(r"^\d{4}([-/]\d{1,2}([-/]\d{1,2})?)?$|^\d{4}-\d{2}-\d{2}[ T]\d{2}:")

MAX_CHART_ROWS = 30
MIN_CHART_ROWS = 2


def _is_number(v: Any) -> bool:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return True
    if isinstance(v, str):
        try:
            float(v)
            return True
        except ValueError:
            return False
    return False


def _is_date_like(v: Any) -> bool:
    return isinstance(v, str) and bool(_DATE_LIKE.match(v.strip()))


def infer_chart(columns: list[str], rows: list[tuple]) -> ChartKind:
    """根据列与数据推断图表类型。"""
    if len(columns) != 2 or not (MIN_CHART_ROWS <= len(rows) <= MAX_CHART_ROWS):
        return "none"
    if not all(_is_number(row[1]) for row in rows):
        return "none"
    first_col = [row[0] for row in rows]
    if all(_is_date_like(v) for v in first_col):
        return "line"
    return "bar"


def chart_frame(columns: list[str], rows: list[tuple]):
    """转成 pandas DataFrame（首列作 index），供 st.bar_chart/st.line_chart 使用。"""
    import pandas as pd

    df = pd.DataFrame(rows, columns=columns)
    df = df.set_index(columns[0])
    df[df.columns[0]] = pd.to_numeric(df[df.columns[0]], errors="coerce")
    return df
