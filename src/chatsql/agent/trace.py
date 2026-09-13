"""trace 记录与落盘。"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from chatsql.agent.state import AgentState, TraceEvent


def make_event(node: str, start: float, summary: str) -> TraceEvent:
    return TraceEvent(node=node, duration_ms=int((time.monotonic() - start) * 1000), summary=summary)


def save_trace(trace_dir: Path, state: AgentState) -> Path | None:
    """把一次问答的 trace 写成 JSONL：首行 meta，中间逐事件，末行结果。"""
    try:
        trace_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        path = trace_dir / f"{ts}.jsonl"
        lines = [
            {"meta": {"question": state.get("question"), "db_path": state.get("db_path"),
                      "time": ts}},
            *({"event": e} for e in state.get("trace", [])),
            {"final": {"status": state.get("status"), "attempts": state.get("attempts"),
                       "sql": state.get("sql_draft"), "answer": state.get("answer")}},
        ]
        path.write_text(
            "\n".join(json.dumps(line, ensure_ascii=False, default=str) for line in lines) + "\n",
            encoding="utf-8",
        )
        return path
    except OSError:
        return None  # trace 落盘失败不影响主流程
