"""检索层：把问题变成“有依据的上下文片段”。

Top-K：只取分数最高的 K 个片段。K 不是越大越好——塞太多无关内容会稀释提示词，
模型反而更容易跑偏（这叫“上下文噪声”）。

相关性阈值：
    向量检索永远会返回“最像的”，哪怕知识库里根本没有相关内容。
    所以必须用 min_score 兜底，低于阈值就判定“无相关资料”，
    再交给业务层回复“暂时无法确认，建议转人工”，绝不能让模型自由发挥业务政策。

为什么阈值要按 embedding 模型区分（而不是一个固定数字）？
    余弦相似度的“绝对数值”取决于向量模型本身。bge-m3 这类语义模型，
    相关文本通常能到 0.5 以上；而本地哈希向量是纯词面匹配，相关文本也只有 0.1~0.3。
    同一个阈值用在这两套模型上，必然一套全过滤、一套全放行。
    所以这里用 provider 自适应的默认阈值，并允许 .env 覆盖。

本地降级模式额外加一道“词面覆盖度”门槛：
    把问题切成字符二元组，看其中有多少比例真的出现在片段里。
    实测无关问题（如“火星探测器什么时候发射”）覆盖度为 0，
    相关的政策问题在 0.2~0.7，区分度比单看余弦更可靠。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from app.config import settings
from app.rag.embeddings import get_embedder
from app.rag.vector_store import SearchHit, get_index

logger = logging.getLogger(__name__)

# 不同 embedding 实现对应的默认相似度阈值
AUTO_MIN_SCORE = {
    "ollama": 0.35,
    # 实测：相关问题组合分 0.26~0.47，无关问题 ≤0.11，0.15 是较稳的分界
    "local-hashing": 0.15,
}
# 本地词面向量的最低词面覆盖度
LOCAL_MIN_COVERAGE = 0.12

_CLEAN = re.compile(r"[^\u4e00-\u9fffa-z0-9]")


def _bigrams(text: str) -> set[str]:
    t = _CLEAN.sub("", text.lower())
    if len(t) < 2:
        return {t} if t else set()
    return {t[i : i + 2] for i in range(len(t) - 1)}


def lexical_coverage(query: str, text: str) -> float:
    """问题里的字符二元组有多大比例出现在片段里。范围 0~1。"""
    q = _bigrams(query)
    if not q:
        return 0.0
    return len(q & _bigrams(text)) / len(q)


@dataclass
class RetrievalResult:
    query: str
    hits: list[SearchHit] = field(default_factory=list)
    top_score: float = 0.0
    has_context: bool = False
    reason: str = ""
    used_provider: str = ""
    threshold: float = 0.0

    def sources(self) -> list[dict]:
        """给前端/数据库用的来源信息，保留可定位的片段编号。"""
        return [
            {
                "document_id": h.document_id,
                "file_name": h.file_name,
                "chunk_index": h.chunk_index,
                "score": round(h.score, 4),
                "snippet": h.text[:160],
            }
            for h in self.hits
        ]


class Retriever:
    def __init__(self, top_k: int | None = None, min_score: float | None = None) -> None:
        self.top_k = top_k or settings.retrieval_top_k
        # 传 None 表示使用自适应阈值；传具体数字则强制覆盖
        self.min_score = min_score if min_score is not None else None

    def _resolve_threshold(self, provider: str) -> float:
        if self.min_score is not None:
            return self.min_score
        if settings.retrieval_min_score > 0:
            return settings.retrieval_min_score
        return AUTO_MIN_SCORE.get(provider, 0.2)

    def retrieve(self, query: str) -> RetrievalResult:
        query = (query or "").strip()
        if not query:
            return RetrievalResult(query=query, reason="empty_query")

        embedder = get_embedder()
        index = get_index()
        if index.size == 0:
            return RetrievalResult(
                query=query, reason="empty_index", used_provider=embedder.name
            )

        threshold = self._resolve_threshold(embedder.name)

        try:
            qvec = embedder.embed([query])[0]
            raw_hits = index.search(qvec, top_k=self.top_k)
        except Exception as exc:  # noqa: BLE001
            logger.exception("检索失败")
            return RetrievalResult(
                query=query,
                reason=f"retrieval_error: {exc}",
                used_provider=embedder.name,
                threshold=threshold,
            )

        is_local = embedder.name == "local-hashing"
        scored: list[SearchHit] = []
        for h in raw_hits:
            if is_local:
                cov = lexical_coverage(query, h.text)
                if cov < LOCAL_MIN_COVERAGE:
                    continue
                # 词面模式下，余弦 + 覆盖度各占一半，排序更贴近“真的讲了这件事”
                combined = 0.5 * h.score + 0.5 * cov
            else:
                combined = h.score
            scored.append(
                SearchHit(h.document_id, h.file_name, h.chunk_index, h.text, combined)
            )

        scored.sort(key=lambda x: x.score, reverse=True)
        kept = [h for h in scored if h.score >= threshold]
        top = max((h.score for h in scored), default=0.0)

        # 片段去重：同一文档相邻片段高度重复时只留分数最高的一个
        deduped: list[SearchHit] = []
        for h in kept:
            if any(
                h.document_id == d.document_id and abs(h.chunk_index - d.chunk_index) <= 1
                for d in deduped
            ):
                continue
            deduped.append(h)

        has_ctx = bool(deduped)
        return RetrievalResult(
            query=query,
            hits=deduped,
            top_score=top,
            has_context=has_ctx,
            reason="ok" if has_ctx else "below_threshold",
            used_provider=embedder.name,
            threshold=round(threshold, 3),
        )


def get_retriever() -> Retriever:
    return Retriever()
