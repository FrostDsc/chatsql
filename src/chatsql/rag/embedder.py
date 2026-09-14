"""Embedding 抽象与实现。

- Embedder：协议，任何实现 encode(texts) -> 单位向量矩阵 的对象
- SentenceTransformerEmbedder：生产用，懒加载模型
- HashEmbedder：测试用，确定性、零依赖、不下载模型
"""
from __future__ import annotations

import hashlib
from typing import Protocol

import numpy as np


class Embedder(Protocol):
    def encode(self, texts: list[str]) -> np.ndarray:
        """返回 (len(texts), dim) 的 L2 归一化向量矩阵。"""
        ...


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self._model_name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)
        return self._model

    def encode(self, texts: list[str]) -> np.ndarray:
        model = self._load()
        return np.asarray(model.encode(texts, normalize_embeddings=True), dtype=np.float32)


class HashEmbedder:
    """确定性假 embedder：把 token 哈希进固定维度。仅供测试。"""

    def __init__(self, dim: int = 64):
        self.dim = dim

    def encode(self, texts: list[str]) -> np.ndarray:
        vecs = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            for token in text.lower().split():
                h = int(hashlib.md5(token.encode()).hexdigest(), 16)
                vecs[i, h % self.dim] += 1.0
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return vecs / norms
