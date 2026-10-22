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
import socket
from abc import ABC, abstractmethod
from urllib.parse import urlparse

import httpx
import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)


class Embedder(ABC):
    name: str = "base"
    dim: int = 0
    is_semantic: bool = False

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
        return {
            "provider": self.name,
            "dim": self.dim,
            "available": True,
            "is_semantic": self.is_semantic,
        }

    def signature(self) -> str:
        """索引指纹：用于检测“换了 embedding 模型但没重建索引”。"""
        return f"{self.name}:{self.dim}"


class LocalHashingEmbedder(Embedder):
    """离线哈希向量：中文按字符 bigram/trigram，英文按单词切分，再做特征哈希。

    原理接近 TF-IDF 的简化版：把每个 n-gram 哈希到固定维度的某一维上并计数，
    最后归一化。相同词组会把同一维“点亮”，所以相似文本的余弦相似度会更高。
    """

    name = "local-hashing"
    is_semantic = False

    def __init__(self, dim: int | None = None) -> None:
        # 注意：这个 4096 来自 EMBEDDING_DIM，是“哈希桶的数量”，
        # 和 bge-m3 的 1024 维没有任何关系。两者不能互相替代，
        # 所以签名里必须带上 provider 名，换模型时才能被检测出来。
        self.dim = dim or settings.embedding_dim

    def health(self) -> dict:
        return {
            "provider": self.name,
            "model": None,
            "dim": self.dim,
            "available": True,
            "is_semantic": False,
            "detail": f"本地哈希向量（{self.dim} 维，词面近似，不是语义模型）",
        }

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
    is_semantic = True

    # 已知模型的真实维度。这里只用于“提前发现配错模型”并给出明确提示，
    # **不作为可信来源**：真正的维度一律以服务返回的向量长度为准（见 embed）。
    # bge-m3 是 1024 维，和本地哈希的 EMBEDDING_DIM=4096 完全无关，不能互相顶替。
    KNOWN_DIMS = {
        "bge-m3": 1024,
        "bge-large": 1024,
        "bge-large-zh": 1024,
        "nomic-embed-text": 768,
        "mxbai-embed-large": 1024,
        "qwen3-embedding": 1024,
    }

    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        self.model = model or settings.ollama_embedding_model
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.dim = 0  # 首次调用后按真实返回确定
        # 探测结果留档：状态页要回答“为什么没连上”，而不是只说“未连接”
        self.last_error: str | None = None
        self.installed_models: list[str] = []

    def _tcp_open(self) -> bool:
        """端口是否有人监听。

        为什么要单独做这一步：本机可能配了 HTTP 代理，访问 127.0.0.1 时
        代理会返回 502 而不是“连接被拒绝”，于是报错变成“HTTP 502”，
        用户会以为 Ollama 报错了，实际上根本没启动。先探 TCP 能给出准确结论。
        """
        parsed = urlparse(self.base_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 11434
        try:
            with socket.create_connection((host, port), timeout=1.5):
                return True
        except OSError:
            return False

    def probe(self) -> bool:
        """探测服务是否可达，并顺手取回已安装模型列表与失败原因。

        只发 /api/tags（轻量），不在这里做 embed —— 探测不该花掉一次推理。
        """
        self.last_error = None
        self.installed_models = []
        try:
            r = httpx.get(f"{self.base_url}/api/tags", timeout=3.0)
        except Exception as exc:  # noqa: BLE001
            self.last_error = (
                "端口未监听（Ollama 未启动）" if not self._tcp_open() else f"{type(exc).__name__}: {exc}"
            )
            return False
        if r.status_code != 200:
            self.last_error = (
                f"端口未监听（Ollama 未启动），代理返回 HTTP {r.status_code}"
                if not self._tcp_open()
                else f"HTTP {r.status_code}"
            )
            return False
        try:
            self.installed_models = [
                str(m.get("name") or m.get("model") or "") for m in (r.json().get("models") or [])
            ]
        except Exception:  # noqa: BLE001
            self.installed_models = []
        return True

    def has_model(self) -> bool:
        """目标模型是否已经 pull 下来。名字可能带 :latest 后缀，做前缀比对。"""
        if not self.installed_models:
            return False
        want = self.model.split(":")[0]
        return any(
            n == self.model or n.split(":")[0] == want for n in self.installed_models if n
        )

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

        if not vectors:
            raise ValueError("Ollama 没有返回任何向量")

        mat = self._normalize(np.array(vectors, dtype=np.float32))
        new_dim = int(mat.shape[1])
        # 同一次进程里维度突然变化，说明服务端换了模型或被改成了别的模型。
        # 这时继续写索引会把两种维度的向量混在一起，必须立刻报错。
        if self.dim and new_dim != self.dim:
            raise ValueError(
                f"Ollama 返回的向量维度从 {self.dim} 变成了 {new_dim}，"
                f"疑似中途更换了模型（当前配置 {self.model}）。请重建索引。"
            )
        expected = self.KNOWN_DIMS.get(self.model.split(":")[0])
        if expected and new_dim != expected:
            logger.warning(
                "模型 %s 的已知维度是 %d，但服务返回 %d —— 以真实返回为准",
                self.model,
                expected,
                new_dim,
            )
        self.dim = new_dim
        return mat

    def signature(self) -> str:
        return f"{self.name}:{self.model}"

    def health(self) -> dict:
        reachable = self.probe()
        ready = reachable and self.has_model()
        if not reachable:
            detail = f"无法连接 {self.base_url}（{self.last_error or '原因未知'}）"
        elif not self.installed_models:
            detail = "Ollama 可访问，但模型列表为空"
        elif not ready:
            detail = (
                f"Ollama 可访问，但未安装模型 {self.model}"
                f"（已安装：{', '.join(m for m in self.installed_models[:5] if m) or '无'}）"
            )
        else:
            detail = f"Ollama 可访问，模型 {self.model} 已安装"
        return {
            "provider": self.name,
            "model": self.model,
            "base_url": self.base_url,
            "dim": self.dim,
            # available 表示“真的能产出向量”，服务通了但模型没 pull 不算可用
            "available": ready,
            "is_semantic": True,
            "service_reachable": reachable,
            "model_installed": ready,
            "installed_models": [m for m in self.installed_models if m],
            "detail": detail,
        }


_embedder: Embedder | None = None
# 记录“为什么选了这个实现”，供 /api/health 与设置页如实展示。
# 只存在内存里：它描述的是**本进程启动时**的探测结果，落库反而会过期误导。
_build_info: dict = {}


def _build_embedder() -> Embedder:
    global _build_info
    mode = (settings.embedding_provider or "auto").strip().lower()
    info: dict = {
        "configured_provider": mode,
        "active_provider": None,
        "model": None,
        "fallback_reason": None,
    }

    if mode == "local":
        emb = LocalHashingEmbedder()
        info.update(active_provider=emb.name)
        logger.info("按配置使用本地哈希向量（%d 维）", emb.dim)

    elif mode in ("auto", "ollama"):
        ollama = OllamaEmbedder()
        reachable = ollama.probe()
        ready = reachable and ollama.has_model()

        if ready:
            info.update(active_provider="ollama", model=ollama.model)
            logger.info("使用 Ollama embedding: %s（%s）", ollama.model, ollama.base_url)
            _build_info = info
            return ollama

        # 降级但要说清原因：只连上服务、却没 pull 模型，和完全连不上是两件事，
        # 用户要做的操作也不同（一个 pull，一个启动服务）。
        if not reachable:
            reason = f"无法连接 Ollama（{ollama.base_url}）：{ollama.last_error or '原因未知'}"
        elif not ollama.installed_models:
            reason = "Ollama 可访问，但没有任何已安装的模型"
        else:
            installed = ", ".join(m for m in ollama.installed_models[:5] if m) or "无"
            reason = f"Ollama 里没有模型 {ollama.model}（已安装：{installed}）"

        info.update(
            active_provider="local-hashing",
            fallback_reason=reason,
        )
        logger.warning("降级为本地哈希向量：%s", reason)
        emb = LocalHashingEmbedder()
    else:
        raise ValueError(f"未知 EMBEDDING_PROVIDER: {settings.embedding_provider}")

    _build_info = info
    return emb


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = _build_embedder()
    return _embedder


def embedding_status() -> dict:
    """给 /api/health 用的完整状态：配置要求什么、实际用了什么、为什么。

    额外做一次**实时**探测：如果进程启动时 Ollama 还没起来、现在起来了，
    这里会告诉用户“重启后端即可切换”，而不是让人对着“未连接”反复刷新。
    """
    emb = get_embedder()
    status = dict(emb.health())
    configured = (_build_info.get("configured_provider") or settings.embedding_provider or "auto").lower()

    status["configured_provider"] = configured
    status["active_provider"] = emb.name
    status["fallback_reason"] = _build_info.get("fallback_reason")
    status["is_fallback"] = emb.name != "ollama" and configured in ("auto", "ollama")
    status["index_dim_note"] = (
        "本地哈希维度来自 EMBEDDING_DIM，与 bge-m3 的 1024 维无关，两者不可混用"
        if emb.name == "local-hashing"
        else None
    )

    if status["is_fallback"]:
        probe = OllamaEmbedder()
        reachable = probe.probe()
        ready = reachable and probe.has_model()
        status["ollama_now_reachable"] = reachable
        status["ollama_model_now_ready"] = ready
        # 现在能用了，但当前进程已经用降级实现建过索引 —— 必须重启才会重新探测
        status["restart_required"] = ready
        if ready:
            status["detail"] = (
                f"当前进程使用本地哈希向量；Ollama 现已可用（{probe.model}），重启后端即可切换"
            )
    return status


def reset_embedder() -> None:
    """测试用：强制下次重新探测。"""
    global _embedder, _build_info
    _embedder = None
    _build_info = {}
