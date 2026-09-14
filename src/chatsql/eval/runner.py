"""评测 runner：在 mini_dev 上批量跑三种配置，输出 details.jsonl（支持断点续跑）。

三种配置：
- direct：阶段 1 单发链路（baseline，无自纠错、无 RAG）
- agent：完整闭环，RAG 关闭（隔离自纠错的贡献）
- agent_rag：完整闭环 + RAG（按 question_id 留一排除）
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from chatsql.agent.graph import ask
from chatsql.agent.trace import save_trace
from chatsql.config import Settings, resolve_db_path
from chatsql.db.executor import execute_readonly
from chatsql.eval.metrics import compare_result_sets
from chatsql.llm.base import LLMClient
from chatsql.pipeline import run_question

CONFIGS = ("direct", "agent", "agent_rag")
MAX_LLM_RETRIES = 3  # 429 等瞬时报错的退避重试


def _run_one(
    config: str,
    sample: dict,
    llm: LLMClient,
    settings: Settings,
    retriever,
) -> dict:
    qid = int(sample["question_id"])
    db_path = resolve_db_path(settings, sample["db_id"])
    record = {
        "question_id": qid, "db_id": sample["db_id"], "difficulty": sample["difficulty"],
        "question": sample["question"], "gold_sql": sample["SQL"],
        "pred_sql": None, "attempts": None, "ex_match": False, "failure": None,
    }

    # gold 先跑：gold 自己失败的题单独归类，不进入分母
    try:
        gold_rows = execute_readonly(db_path, sample["SQL"], timeout_seconds=settings.exec_timeout,
                                     max_rows=10_000).rows
    except Exception as e:
        record["failure"] = "gold_exec_error"
        record["error"] = str(e)
        return record

    # 带退避的预测执行
    state_or_result = None
    for attempt in range(MAX_LLM_RETRIES):
        try:
            if config == "direct":
                state_or_result = run_question(
                    llm, db_path, sample["question"],
                    exec_timeout=settings.exec_timeout, max_rows=10_000)
            else:
                state_or_result = ask(
                    llm, settings, db_path, sample["question"],
                    save_trace_to=None,
                    retriever=None if config == "agent" else retriever,
                    exclude_question_ids=[qid] if config == "agent_rag" else None,
                    with_answer=False)
            break
        except Exception as e:
            if attempt == MAX_LLM_RETRIES - 1:
                record["failure"] = "pipeline_error"
                record["error"] = f"{type(e).__name__}: {e}"
                return record
            time.sleep(2 ** attempt * 2)

    if config == "direct":
        record["pred_sql"] = state_or_result.sql
        record["attempts"] = 1
        if not state_or_result.ok:
            record["failure"] = "exec_error"
            record["error"] = state_or_result.error
            return record
        pred_rows = state_or_result.query_result.rows
    else:
        record["pred_sql"] = state_or_result.get("sql_draft")
        record["attempts"] = state_or_result.get("attempts")
        record["_state"] = state_or_result  # 供失败 trace 落盘
        if state_or_result.get("status") == "declined":
            record["failure"] = "declined"
            return record
        if state_or_result.get("query_result") is None:
            record["failure"] = "exec_error"
            return record
        pred_rows = state_or_result["query_result"]["rows"]

    record["ex_match"] = compare_result_sets(pred_rows, gold_rows)
    if not record["ex_match"]:
        record["failure"] = "result_mismatch"
    return record


def run_eval(
    config: str,
    llm: LLMClient,
    settings: Settings,
    data_json: Path,
    out_dir: Path,
    limit: int | None = None,
    workers: int = 4,
    retriever=None,
    db_filter: str | None = None,
    difficulty_filter: str | None = None,
) -> Path:
    """跑一组配置的评测，返回 details.jsonl 路径。已完成的 question_id 自动跳过。"""
    assert config in CONFIGS, f"未知配置 {config}，可选：{CONFIGS}"
    out_dir.mkdir(parents=True, exist_ok=True)
    details_path = out_dir / "details.jsonl"

    samples = json.loads(data_json.read_text(encoding="utf-8"))
    if db_filter:
        samples = [s for s in samples if s["db_id"] == db_filter]
    if difficulty_filter:
        samples = [s for s in samples if s["difficulty"] == difficulty_filter]
    if limit:
        samples = samples[:limit]

    done_ids = set()
    if details_path.exists():
        for line in details_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done_ids.add(json.loads(line)["question_id"])
    todo = [s for s in samples if int(s["question_id"]) not in done_ids]
    print(f"[{config}] 共 {len(samples)} 题，已完成 {len(done_ids)}，本次跑 {len(todo)} 题")

    traces_dir = out_dir / "traces"
    correct = 0
    with open(details_path, "a", encoding="utf-8") as f:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_run_one, config, s, llm, settings, retriever): s
                for s in todo
            }
            for i, fut in enumerate(as_completed(futures), 1):
                record = fut.result()
                state = record.pop("_state", None)
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
                f.flush()
                correct += record["ex_match"]
                if not record["ex_match"] and state is not None:
                    save_trace(traces_dir, state)
                if i % 10 == 0 or i == len(todo):
                    print(f"  [{config}] {i}/{len(todo)} 本次正确率 {correct}/{i}", flush=True)

    return details_path
