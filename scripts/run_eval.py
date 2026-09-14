"""评测入口。

用法：
    uv run python scripts/run_eval.py --config direct --limit 30     # 冒烟
    uv run python scripts/run_eval.py --config agent_rag             # 全量 500 题
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from chatsql.config import load_settings  # noqa: E402
from chatsql.eval.runner import CONFIGS, run_eval  # noqa: E402
from chatsql.llm.factory import create_llm  # noqa: E402

DATA_JSON = PROJECT_ROOT / "data" / "mini_dev_data" / "mini_dev_sqlite.json"
REPORTS_ROOT = PROJECT_ROOT / "eval" / "reports"


def main() -> int:
    parser = argparse.ArgumentParser(description="ChatSQL 评测 runner")
    parser.add_argument("--config", required=True, choices=CONFIGS)
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 题（冒烟用）")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--tag", default=None, help="运行标签，默认 <config>_<时间戳>；续跑时传同一标签")
    args = parser.parse_args()

    settings = load_settings()
    if settings.use_mock:
        print("当前是 mock 模式，评测请配置真实 API key")
        return 1
    if not DATA_JSON.exists():
        print("未找到 mini_dev 数据，请先运行 scripts/download_data.py")
        return 1

    retriever = None
    if args.config == "agent_rag":
        from chatsql.rag.embedder import SentenceTransformerEmbedder
        from chatsql.rag.retriever import Retriever
        embedder = SentenceTransformerEmbedder(settings.rag.embedding_model)
        print("预热 embedding 模型...")
        embedder.encode(["warmup"])  # 主线程先加载，避免多线程并发首载
        retriever = Retriever(settings.rag.index_dir, embedder)

    tag = args.tag or f"{args.config}_{datetime.now():%Y%m%d-%H%M%S}"
    out_dir = REPORTS_ROOT / tag

    llm = create_llm(settings)
    details = run_eval(args.config, llm, settings, DATA_JSON, out_dir,
                       limit=args.limit, workers=args.workers, retriever=retriever)
    print(f"\n明细已写入 {details}")
    print(f"续跑同一批次：--config {args.config} --tag {tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
