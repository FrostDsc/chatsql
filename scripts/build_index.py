"""为全部 mini_dev 数据库构建 RAG 向量索引。

用法：uv run python scripts/build_index.py
首次运行会下载 embedding 模型（all-MiniLM-L6-v2，约 90MB）。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from chatsql.config import load_settings  # noqa: E402
from chatsql.rag.embedder import SentenceTransformerEmbedder  # noqa: E402
from chatsql.rag.indexer import build_docs_for_db  # noqa: E402
from chatsql.rag.store import VectorStore  # noqa: E402

DATA_JSON = PROJECT_ROOT / "data" / "mini_dev_data" / "mini_dev_sqlite.json"


def main() -> int:
    settings = load_settings()
    db_root = settings.db_root
    if not DATA_JSON.exists():
        print("未找到 mini_dev 数据，请先运行 scripts/download_data.py")
        return 1

    db_ids = sorted(p.name for p in db_root.iterdir() if (p / f"{p.name}.sqlite").exists())
    print(f"共 {len(db_ids)} 个数据库，embedding 模型：{settings.rag.embedding_model}")
    embedder = SentenceTransformerEmbedder(settings.rag.embedding_model)

    t0 = time.monotonic()
    for db_id in db_ids:
        docs = build_docs_for_db(db_root, DATA_JSON, db_id)
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
