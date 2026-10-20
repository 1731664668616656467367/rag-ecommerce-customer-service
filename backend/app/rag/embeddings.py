"""Embedding（向量化）模块。

概念：embedding 就是把一段文字映射成一串数字（向量）。语义相近的两段文字，
向量在空间里的方向也接近。于是“找相关资料”就变成“找方向最接近的向量”，
可以用余弦相似度算出一个 0~1 的分数。

本模块提供两种实现，运行时可切换，绝不假装某个服务可用：

1. OllamaEmbedder —— 调用本机 Ollama 的 bge-m3 模型，语义效果最好。
   前提：Ollama 已启动，且已 pull bge-m3。
2. LocalHashingEmbedder —— 纯离线、零依赖的字符 n-gram 哈希向量。
   效果弱于 bge-m3（更接近“关键词匹配”），但保证系统在没有 Ollama 时依然能跑、
   能测、能演示。这不是“假的 RAG”，检索与打分逻辑完全真实，只是向量质量不同。

选择逻辑由 EMBEDDING_PROVIDER 控制：auto 时探测 Ollama，失败则降级。
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
from abc import ABC, abstractmethod

import httpx
import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)


class Embedder(ABC):
    name: str = "base"
    dim: int = 0

    @abstractmethod
    def embed(self, texts: list[str]) -> np.ndarray:
        """输入 N 段文本，返回形状 (N, dim) 的 float32 矩阵，且每行已 L2 归一化。"""

    @staticmethod
    def _normalize(mat: np.ndarray) -> np.ndarray:
        mat = np.asarray(mat, dtype=np.float32)
        if mat.ndim == 1:
            mat = mat.reshape(1, -1)
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return mat / norms

    def health(self) -> dict:
        return {"provider": self.name, "dim": self.dim, "available": True}


class LocalHashingEmbedder(Embedder):
    """离线哈希向量：中文按字符 bigram/trigram，英文按单词切分，再做特征哈希。

    原理接近 TF-IDF 的简化版：把每个 n-gram 哈希到固定维度的某一维上并计数，
    最后归一化。相同词组会把同一维“点亮”，所以相似文本的余弦相似度会更高。
    """

    name = "local-hashing"

    def __init__(self, dim: int | None = None) -> None:
        self.dim = dim or settings.embedding_dim

    _token_re = re.compile(r"[a-zA-Z0-9_]+")
    _cjk_re = re.compile(r"[\u4e00-\u9fff]")

    def _features(self, text: str) -> list[str]:
        text = text.lower()
        feats: list[str] = []
        # 英文/数字词
        for w in self._token_re.findall(text):
            if len(w) > 1:
                feats.append("w:" + w)
        # 中文 n-gram
        for seg in re.findall(r"[\u4e00-\u9fff]+", text):
            for n in (1, 2, 3):
                for i in range(len(seg) - n + 1):
                    feats.append(f"c{n}:" + seg[i : i + n])
        return feats

    def _one(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        feats = self._features(text)
        if not feats:
            return vec
        counts: dict[str, int] = {}
        for f in feats:
            counts[f] = counts.get(f, 0) + 1
        for f, c in counts.items():
            h = int.from_bytes(hashlib.blake2b(f.encode("utf-8"), digest_size=8).digest(), "little")
            idx = h % self.dim
            sign = 1.0 if (h >> 63) & 1 == 0 else -1.0
            # 次线性 TF，抑制长文本里高频词的权重
            vec[idx] += sign * (1.0 + math.log(c))
        return vec

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return self._normalize(np.vstack([self._one(t) for t in texts]))


class OllamaEmbedder(Embedder):
    name = "ollama"

    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        self.model = model or settings.ollama_embedding_model
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.dim = 0  # 首次调用后确定

    def probe(self) -> bool:
        try:
            r = httpx.get(f"{self.base_url}/api/tags", timeout=3.0)
            return r.status_code == 200
        except Exception:
            return False

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim or 1), dtype=np.float32)
        vectors: list[list[float]] = []
        # 用 /api/embed（新版批量接口），失败再退回 /api/embeddings（单条）
        try:
            r = httpx.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": texts},
                timeout=settings.ollama_timeout_seconds,
            )
            r.raise_for_status()
            vectors = r.json()["embeddings"]
        except Exception as exc:  # noqa: BLE001
            logger.warning("批量 embedding 失败，尝试单条接口: %s", exc)
            for t in texts:
                r = httpx.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model, "prompt": t},
                    timeout=settings.ollama_timeout_seconds,
                )
                r.raise_for_status()
                vectors.append(r.json()["embedding"])
        mat = self._normalize(np.array(vectors, dtype=np.float32))
        self.dim = mat.shape[1]
        return mat

    def health(self) -> dict:
        ok = self.probe()
        return {
            "provider": self.name,
            "model": self.model,
            "available": ok,
            "detail": "Ollama 可访问" if ok else "无法连接 Ollama，已降级",
        }


_embedder: Embedder | None = None


def _build_embedder() -> Embedder:
    mode = settings.embedding_provider.lower()
    if mode == "local":
        return LocalHashingEmbedder()
    if mode in ("auto", "ollama"):
        ollama = OllamaEmbedder()
        if ollama.probe():
            logger.info("使用 Ollama embedding: %s", ollama.model)
            return ollama
        if mode == "ollama":
            logger.warning("配置要求 Ollama 但连接失败，仍降级到本地向量")
        else:
            logger.warning("未探测到 Ollama，使用本地哈希向量（效果弱于 bge-m3）")
        return LocalHashingEmbedder()
    raise ValueError(f"未知 EMBEDDING_PROVIDER: {settings.embedding_provider}")


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = _build_embedder()
    return _embedder


def reset_embedder() -> None:
    """测试用：强制下次重新探测。"""
    global _embedder
    _embedder = None
