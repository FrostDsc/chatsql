"""ChatSQL CLI：对 BIRD mini_dev 数据库提问。

用法：
    uv run python cli.py --db california_schools "Free/Reduced Meal 比例最高的学校是哪所？"
"""
from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.panel import Panel

from chatsql.config import load_settings, resolve_db_path
from chatsql.llm.factory import create_llm
from chatsql.pipeline import run_question

console = Console()


def main() -> int:
    parser = argparse.ArgumentParser(description="ChatSQL：用自然语言查询 SQLite 数据库")
    parser.add_argument("question", help="自然语言问题")
    parser.add_argument("--db", required=True, help="mini_dev 数据库名，如 california_schools")
    parser.add_argument("--config", default=None, help="配置文件路径，默认 configs/settings.yaml")
    parser.add_argument("--show-raw", action="store_true", help="打印模型原始回复")
    args = parser.parse_args()

    settings = load_settings(args.config)
    try:
        db_path = resolve_db_path(settings, args.db)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        return 1

    llm = create_llm(settings)
    if settings.use_mock:
        console.print("[yellow]提示：未配置 API key，当前为 mock 模式（返回固定 SQL）[/yellow]")

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


if __name__ == "__main__":
    sys.exit(main())
