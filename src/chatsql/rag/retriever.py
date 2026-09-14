"""检索器：按库加载索引，embed 问题，分组返回检索结果。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from chatsql.rag.embedder import Embedder
from chatsql.rag.store import Doc, VectorStore


@dataclass
class RetrievalResult:
    examples: list[Doc] = field(default_factory=list)
    knowledge: list[Doc] = field(default_factory=list)  # knowledge + column_doc 混合排序


class Retriever:
    def __init__(self, index_dir: str | Path, embedder: Embedder):
        self._index_dir = Path(index_dir)
        self._embedder = embedder
        self._cache: dict[str, VectorStore] = {}

    def available(self, db_id: str) -> bool:
        return VectorStore.exists(self._index_dir, db_id)

    def _store(self, db_id: str) -> VectorStore:
        if db_id not in self._cache:
            self._cache[db_id] = VectorStore.load(self._index_dir, db_id)
        return self._cache[db_id]

    def retrieve(
        self,
        db_id: str,
        question: str,
        top_k_examples: int = 3,
        top_k_knowledge: int = 3,
        exclude_question_ids: set[int] | None = None,
    ) -> RetrievalResult:
        store = self._store(db_id)
        qvec = self._embedder.encode([question])[0]
        return RetrievalResult(
            examples=store.search(qvec, top_k=top_k_examples, kinds={"example"},
                                  exclude_question_ids=exclude_question_ids),
            knowledge=store.search(qvec, top_k=top_k_knowledge, kinds={"knowledge", "column_doc"},
                                   exclude_question_ids=exclude_question_ids),
        )
