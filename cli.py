"""ChatSQL CLI：对 BIRD mini_dev 数据库提问。

用法：
    单问：  uv run python cli.py --db california_schools "How many schools are there?"
    多轮：  uv run python cli.py --db student_club --chat
    调试：  加 --verbose 打印 Agent trace；--mode direct 使用阶段 1 的单发链路（baseline）
"""
from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.panel import Panel

from chatsql.agent.graph import _UNSET, ask
from chatsql.config import Settings, load_settings, resolve_db_path
from chatsql.llm.base import Message
from chatsql.pipeline import run_question

console = Console()


def _print_trace(state) -> None:
    lines = [
        f"[dim]{e['node']:<18} {e['duration_ms']:>6}ms[/dim]  {e['summary']}"
        for e in state.get("trace", [])
    ]
    console.print(Panel("\n".join(lines), title="Agent trace", border_style="dim"))


def run_agent_question(llm, settings: Settings, db_path, question: str,
                       history: list[Message], verbose: bool, use_rag: bool = True):
    """跑一轮 Agent 问答并渲染输出，返回最终状态。"""
    state = ask(llm, settings, db_path, question, dialogue_history=history,
                retriever=None if not use_rag else _UNSET)
    console.print(Panel(state.get("sql_draft", ""), title="SQL", border_style="cyan"))
    qr = state.get("query_result")
    if qr:
        from chatsql.db.executor import QueryResult
        result = QueryResult(columns=qr["columns"], rows=qr["rows"], truncated=qr["truncated"])
        console.print(Panel(result.to_markdown(), title="查询结果", border_style="green"))
    style = "green" if state.get("status") == "ok" else "yellow"
    console.print(Panel(state.get("answer", ""), title="回答", border_style=style))
    if verbose:
        _print_trace(state)
    return state


def chat_loop(llm, settings: Settings, db_path, verbose: bool, use_rag: bool = True) -> int:
    console.print("[bold]进入多轮对话模式[/bold]，输入 exit/quit 退出")
    history: list[Message] = []
    while True:
        try:
            question = console.input("\n[bold cyan]你：[/bold cyan]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n再见！")
            return 0
        if not question or question.lower() in ("exit", "quit"):
            console.print("再见！")
            return 0

        state = run_agent_question(llm, settings, db_path, question, history, verbose, use_rag)
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": state.get("answer", "")})


def main() -> int:
    parser = argparse.ArgumentParser(description="ChatSQL：用自然语言查询 SQLite 数据库")
    parser.add_argument("question", nargs="?", default=None, help="自然语言问题（--chat 时省略）")
    parser.add_argument("--db", required=True, help="mini_dev 数据库名，如 california_schools")
    parser.add_argument("--config", default=None, help="配置文件路径，默认 configs/settings.yaml")
    parser.add_argument("--chat", action="store_true", help="多轮对话模式")
    parser.add_argument("--verbose", action="store_true", help="打印 Agent trace")
    parser.add_argument("--mode", choices=["agent", "direct"], default="agent",
                        help="agent=完整闭环（默认）；direct=阶段 1 单发链路（baseline）")
    parser.add_argument("--show-raw", action="store_true", help="(direct 模式) 打印模型原始回复")
    parser.add_argument("--no-rag", action="store_true", help="关闭 RAG 检索（消融对比用）")
    args = parser.parse_args()

    settings = load_settings(args.config)
    try:
        db_path = resolve_db_path(settings, args.db)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        return 1

    from chatsql.llm.factory import create_llm
    llm = create_llm(settings)
    if settings.use_mock:
        console.print("[yellow]提示：未配置 API key，当前为 mock 模式[/yellow]")

    if args.chat:
        return chat_loop(llm, settings, db_path, args.verbose, use_rag=not args.no_rag)

    if not args.question:
        parser.error("请提供问题，或使用 --chat 进入多轮对话")

    if args.mode == "direct":
        result = run_question(
            llm, db_path, args.question,
            exec_timeout=settings.exec_timeout, max_rows=settings.exec_max_rows,
        )
        console.print(Panel(result.sql, title="生成的 SQL", border_style="cyan"))
        if args.show_raw:
            console.print(Panel(result.raw_response, title="模型原始回复", border_style="dim"))
        if not result.ok:
            console.print(f"[red]执行失败：{result.error}[/red]")
            return 1
        console.print(Panel(result.query_result.to_markdown(), title="查询结果", border_style="green"))
        return 0

    run_agent_question(llm, settings, db_path, args.question, [], args.verbose,
                       use_rag=not args.no_rag)
    return 0


if __name__ == "__main__":
    sys.exit(main())
