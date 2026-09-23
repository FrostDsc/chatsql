"""Spider gold SQL 的难度启发式评估。

Spider 官方没有给 dev 集逐题难度标签（官方 hardness 是评测脚本里的 SQL 组件计数）。
这里用 sqlglot 解析做简化版：按子句/连接/聚合/嵌套/集合操作加权计分，分四档。
注意：该口径与 BIRD 的 simple/moderate/challenging 标注不同，不可横比。
"""
from __future__ import annotations

import sqlglot
from sqlglot import expressions as exp

LEVELS = ("easy", "medium", "hard", "extra")


def estimate_hardness(sql: str) -> str:
    """按 SQL 结构复杂度给难度分档：easy / medium / hard / extra。

    计分：WHERE/GROUP/ORDER/LIMIT/HAVING 各 1 分，每个 JOIN 1 分，聚合最多 2 分，
    嵌套子查询与 UNION/EXCEPT/INTERSECT 各 3 分（官方口径里它们直接抬档）。
    """
    try:
        stmts = [s for s in sqlglot.parse(sql, read="sqlite") if s is not None]
    except Exception:
        return "easy"  # 解析失败不挡转换流程（gold 基本都能解析）
    if len(stmts) != 1:
        return "hard"
    tree = stmts[0]

    clauses = 0
    for t in (exp.Where, exp.Group, exp.Order, exp.Having, exp.Limit):
        if list(tree.find_all(t)):
            clauses += 1
    joins = len(list(tree.find_all(exp.Join)))
    aggs = min(len(list(tree.find_all(exp.AggFunc))), 2)
    nested = max(len(list(tree.find_all(exp.Select))) - 1, 0)
    sets = len(list(tree.find_all((exp.Union, exp.Except, exp.Intersect))))

    score = clauses + joins + aggs + 3 * (nested + sets)
    if score <= 1:
        return "easy"
    if score <= 4:
        return "medium"
    if score <= 7:
        return "hard"
    return "extra"
