"""为数据库构建 RAG 向量索引。

用法：
  uv run python scripts/build_index.py                        # BIRD mini_dev 全量
  uv run python scripts/build_index.py --data-json my_qa.json # 用自己的问答对（BIRD 格式）
没有问答对文件时自动降级为只索引列描述（database_description/）。
首次运行会下载 embedding 模型（all-MiniLM-L6-v2，约 90MB）。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from chatsql.config import load_settings  # noqa: E402
from chatsql.rag.embedder import SentenceTransformerEmbedder  # noqa: E402
from chatsql.rag.indexer import build_docs_for_db  # noqa: E402
from chatsql.rag.store import VectorStore  # noqa: E402

DEFAULT_DATA_JSON = PROJECT_ROOT / "data" / "mini_dev_data" / "mini_dev_sqlite.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="构建 RAG 向量索引")
    parser.add_argument("--data-json", type=Path, default=None,
                        help="问答对 JSON（BIRD mini_dev 格式）；默认用 mini_dev 自带文件，不存在则只索引列描述")
    args = parser.parse_args()

    settings = load_settings()
    db_root = settings.db_root
    if not db_root.is_dir():
        print(f"数据库目录不存在：{db_root}\n请先运行 scripts/download_data.py，或用 CHATSQL_DB_ROOT 指向自己的库目录")
        return 1

    data_json = args.data_json or DEFAULT_DATA_JSON
    if data_json.exists():
        print(f"问答对文件：{data_json}")
    else:
        if args.data_json:
            print(f"警告：{data_json} 不存在，", end="")
        print("未找到问答对文件，只索引列描述（database_description/）")
        data_json = None

    db_ids = sorted(p.name for p in db_root.iterdir() if (p / f"{p.name}.sqlite").exists())
    print(f"共 {len(db_ids)} 个数据库，embedding 模型：{settings.rag.embedding_model}")
    embedder = SentenceTransformerEmbedder(settings.rag.embedding_model)

    t0 = time.monotonic()
    for db_id in db_ids:
        docs = build_docs_for_db(db_root, data_json, db_id)
        if not docs:
            print(f"  {db_id}: 无问答对也无列描述，跳过")
            continue
        vectors = embedder.encode([d.text for d in docs])
        VectorStore.build(docs, vectors).save(settings.rag.index_dir, db_id)
        by_kind = {}
        for d in docs:
            by_kind[d.kind] = by_kind.get(d.kind, 0) + 1
        print(f"  {db_id}: {len(docs)} 条文档 {by_kind}")

    print(f"\n完成，耗时 {time.monotonic() - t0:.1f}s，索引位于 {settings.rag.index_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
