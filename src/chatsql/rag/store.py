"""极简向量库：numpy 余弦相似度 + top-k 检索，npz/jsonl 持久化。

规模假设：单库文档数百条，暴力检索毫秒级，无需近似最近邻。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass
class Doc:
    text: str
    kind: str                      # "example" | "knowledge" | "column_doc"
    question_id: int | None = None  # 留一排除用；column_doc 为 None


@dataclass
class VectorStore:
    docs: list[Doc] = field(default_factory=list)
    vectors: np.ndarray | None = None  # (n, dim)，已归一化

    @classmethod
    def build(cls, docs: list[Doc], vectors: np.ndarray) -> "VectorStore":
        if len(docs) != len(vectors):
            raise ValueError(f"docs({len(docs)}) 与 vectors({len(vectors)}) 数量不一致")
        return cls(docs=docs, vectors=vectors.astype(np.float32))

    def search(
        self,
        query_vec: np.ndarray,
        top_k: int = 3,
        kinds: set[str] | None = None,
        exclude_question_ids: set[int] | None = None,
    ) -> list[Doc]:
        if self.vectors is None or len(self.docs) == 0:
            return []
        exclude_question_ids = exclude_question_ids or set()
        scores = self.vectors @ query_vec  # 均已归一化，点积即余弦相似度
        ranked = np.argsort(-scores)
        hits: list[Doc] = []
        for idx in ranked:
            doc = self.docs[int(idx)]
            if kinds is not None and doc.kind not in kinds:
                continue
            if doc.question_id is not None and doc.question_id in exclude_question_ids:
                continue
            hits.append(doc)
            if len(hits) == top_k:
                break
        return hits

    def save(self, dir_path: str | Path, name: str) -> None:
        dir_path = Path(dir_path)
        dir_path.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(dir_path / f"{name}.npz", vectors=self.vectors)
        with open(dir_path / f"{name}.jsonl", "w", encoding="utf-8") as f:
            for doc in self.docs:
                f.write(json.dumps({"text": doc.text, "kind": doc.kind,
                                    "question_id": doc.question_id}, ensure_ascii=False) + "\n")

    @classmethod
    def load(cls, dir_path: str | Path, name: str) -> "VectorStore":
        dir_path = Path(dir_path)
        npz = np.load(dir_path / f"{name}.npz")
        vectors = npz["vectors"]
        docs = []
        with open(dir_path / f"{name}.jsonl", encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                docs.append(Doc(text=d["text"], kind=d["kind"], question_id=d.get("question_id")))
        return cls.build(docs, vectors)

    @staticmethod
    def exists(dir_path: str | Path, name: str) -> bool:
        dir_path = Path(dir_path)
        return (dir_path / f"{name}.npz").exists() and (dir_path / f"{name}.jsonl").exists()
