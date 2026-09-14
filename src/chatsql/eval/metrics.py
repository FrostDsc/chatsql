"""评测指标：Execution Accuracy 与分组统计。"""
from __future__ import annotations

from collections import Counter
from typing import Any


def normalize_rows(rows: list[tuple]) -> frozenset:
    """行集合归一化：cell 转字符串，忽略行序与列名。浮点统一转字符串表示。"""
    return frozenset(tuple("NULL" if v is None else str(v) for v in row) for row in rows)


def compare_result_sets(pred_rows: list[tuple], gold_rows: list[tuple]) -> bool:
    return normalize_rows(pred_rows) == normalize_rows(gold_rows)


def ex_accuracy(details: list[dict]) -> float:
    """EX = 执行结果一致的题数 / 有效题数（gold 执行失败的题从分母剔除）。"""
    valid = [d for d in details if d.get("failure") != "gold_exec_error"]
    if not valid:
        return 0.0
    return sum(1 for d in valid if d.get("ex_match")) / len(valid)


def breakdown(details: list[dict], key: str) -> dict[str, dict[str, Any]]:
    """按某个字段（difficulty / db_id）分组统计 EX。"""
    groups: dict[str, list[dict]] = {}
    for d in details:
        if d.get("failure") == "gold_exec_error":
            continue
        groups.setdefault(d.get(key, "?"), []).append(d)
    return {
        k: {"n": len(v), "correct": sum(1 for d in v if d.get("ex_match")),
            "ex": round(sum(1 for d in v if d.get("ex_match")) / len(v), 4)}
        for k, v in sorted(groups.items())
    }


def failure_categories(details: list[dict]) -> Counter:
    return Counter(d["failure"] for d in details if not d.get("ex_match") and d.get("failure"))
