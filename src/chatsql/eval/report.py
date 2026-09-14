"""报告生成：读取多组 details.jsonl，产出消融对比 markdown。"""
from __future__ import annotations

import json
from pathlib import Path

from chatsql.eval.metrics import breakdown, ex_accuracy, failure_categories
from chatsql.eval.runner import CONFIGS

CONFIG_LABELS = {
    "direct": "baseline（单发直出）",
    "agent": "+ 自纠错",
    "agent_rag": "+ 自纠错 + RAG",
}


def load_details(run_dir: Path) -> list[dict]:
    path = run_dir / "details.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _config_name(run_dir: Path) -> str:
    name = run_dir.name
    for cfg in sorted(CONFIGS, key=len, reverse=True):  # agent_rag 比 agent 长，先匹配长的
        if name == cfg or name.startswith(cfg + "_") or name.endswith("_" + cfg):
            return cfg
    return name


def _fmt_pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def build_report(run_dirs: list[Path], model_name: str, report_date: str) -> str:
    runs = {(_config_name(d)): load_details(d) for d in run_dirs}

    lines = [
        "# ChatSQL BIRD mini_dev 评测报告",
        "",
        f"- 模型：`{model_name}`（temperature=0）",
        f"- 日期：{report_date}",
        f"- 指标：Execution Accuracy（预测 SQL 与 gold SQL 执行结果集合相等）",
        "- RAG 评测纪律：留一排除当前题的 question_id，防数据泄漏",
        "",
        "## 总体结果",
        "",
        "| 配置 | EX | 正确/总数 | 平均尝试次数 | 失败数 |",
        "|---|---|---|---|---|",
    ]
    for cfg, details in runs.items():
        valid = [d for d in details if d.get("failure") != "gold_exec_error"]
        avg_attempts = sum(d["attempts"] or 1 for d in valid) / max(len(valid), 1)
        lines.append(
            f"| {CONFIG_LABELS.get(cfg, cfg)} | **{_fmt_pct(ex_accuracy(details))}** | "
            f"{sum(1 for d in valid if d['ex_match'])}/{len(valid)} | "
            f"{avg_attempts:.2f} | {len(valid) - sum(1 for d in valid if d['ex_match'])} |"
        )

    lines += ["", "## 按难度分组", "", "| 难度 | " + " | ".join(CONFIG_LABELS.get(c, c) for c in runs) + " |",
              "|---|" + "---|" * len(runs)]
    all_difficulties = sorted({d["difficulty"] for details in runs.values() for d in details})
    for diff in all_difficulties:
        cells = []
        for details in runs.values():
            bd = breakdown(details, "difficulty").get(diff)
            cells.append(f"{_fmt_pct(bd['ex'])} ({bd['correct']}/{bd['n']})" if bd else "-")
        lines.append(f"| {diff} | " + " | ".join(cells) + " |")

    lines += ["", "## 按数据库分组", "", "| 数据库 | " + " | ".join(CONFIG_LABELS.get(c, c) for c in runs) + " |",
              "|---|" + "---|" * len(runs)]
    all_dbs = sorted({d["db_id"] for details in runs.values() for d in details})
    for db in all_dbs:
        cells = []
        for details in runs.values():
            bd = breakdown(details, "db_id").get(db)
            cells.append(f"{_fmt_pct(bd['ex'])} ({bd['correct']}/{bd['n']})" if bd else "-")
        lines.append(f"| {db} | " + " | ".join(cells) + " |")

    lines += ["", "## 失败分类", "", "| 类别 | " + " | ".join(CONFIG_LABELS.get(c, c) for c in runs) + " |",
              "|---|" + "---|" * len(runs)]
    all_failures = sorted({f for details in runs.values() for f in failure_categories(details)})
    for cat in all_failures:
        cells = [str(failure_categories(details).get(cat, 0)) for details in runs.values()]
        lines.append(f"| {cat} | " + " | ".join(cells) + " |")

    # 典型失败样例：取最完整配置里仍答错的题
    best_cfg = "agent_rag" if "agent_rag" in runs else list(runs)[-1]
    wrong = [d for d in runs[best_cfg] if not d.get("ex_match") and d.get("failure") not in (None, "gold_exec_error")]
    lines += ["", f"## 典型失败样例（{CONFIG_LABELS.get(best_cfg, best_cfg)}，前 5 条）", ""]
    for d in wrong[:5]:
        lines += [
            f"### [{d['question_id']}] {d['db_id']} / {d['difficulty']}",
            "",
            f"**问题**：{d['question']}",
            "",
            f"**失败类别**：{d['failure']}",
            "",
            "```sql",
            (d.get("pred_sql") or "").strip(),
            "```",
            "",
        ]
    return "\n".join(lines)
