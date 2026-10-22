"""检索层：把问题变成“有依据的上下文片段”。

支持两种通道，可配置组合（RETRIEVAL_MODE）：
    1. vector —— 向量余弦检索。语义模型（bge-m3）下效果好；本地哈希向量下只是词面近似。
    2. bm25   —— 传统词法检索（IDF + 长度归一化），不依赖任何模型，精确匹配术语很强。

hybrid（默认）会把两路结果用 RRF 融合。原因很实际：
    纯向量在没有 Ollama 时召回不稳，纯 BM25 又不懂同义词，两者互补。

Top-K：只取分数最高的 K 个片段。K 不是越大越好——塞太多无关内容会稀释提示词。

相关性门槛（为什么必须有两道）：
    检索永远会返回“最像的”，哪怕知识库根本没有相关内容。所以：
    - 向量通道：分数低于阈值直接丢弃；
    - 词法通道：问题里的词必须有足够“分量”真的出现在片段里，且仅按出现比例不够，
      必须按词的区分度加权（见 lexical.CorpusStats）——否则“你们支持火星配送吗？”
      会因为在某段配送范围里撞上“配送”两个字就被当成可靠答案。
    任何一个通道单独命中都算“有依据”；两个通道都不达标，就明确告诉用户“没找到”。

阈值为什么按模型区分：
    余弦相似度的绝对值取决于向量模型。bge-m3 相关文本常到 0.5+，本地哈希只有 0.1~0.3。
    同一个阈值套两套模型，必然一套全过滤、一套全放行。
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

from app.config import settings
from app.rag import lexical
from app.rag.embeddings import get_embedder
from app.rag.vector_store import SearchHit, get_index

logger = logging.getLogger(__name__)

# 不同 embedding 实现对应的默认相似度阈值
AUTO_MIN_SCORE = {
    # bge-m3 的余弦基线明显偏高：不相关的中文短句之间也常有 0.3~0.5。
    # 用 0.35 会把这些无关问题全部放进来（实测“今天股市怎么样”=0.372 被当成有依据）。
    # 下面这个值来自 2026-10-21 的实测（当前 5 篇文档 / 9 个片段）：
    #   15 条真问题最高余弦 0.584~0.781，12 条无关问题 0.282~0.528，两者可分。
    # 取 0.55：两边各留约 0.03 余量，样本内 100% 召回 + 100% 拒答。
    # 换语料/换模型后必须重跑 scripts/eval_retrieval.py 重新校准。
    "ollama": 0.55,
    # 实测：相关问题组合分 0.26~0.47，无关问题 ≤0.11，0.15 是较稳的分界
    "local-hashing": 0.15,
}

# 本地词面向量的最低词面覆盖度（加权，见 lexical.CorpusStats）。
# 0.12 来自 scripts/eval_retrieval.py 的实测（当前 5 篇文档 / 9 个片段）：
#   8 条无关问题最高 0.091（“今天天气怎么样”），10 条真问题最低 0.143，取两者中点。
# 换知识库或换分块参数后请重跑该脚本重新校准，不要凭手感调。
LOCAL_MIN_COVERAGE = 0.12
# BM25 通道单独成候选时，用同一把尺子（词法通道本来就是词面匹配）
LEXICAL_MIN_COVERAGE = 0.12
# RRF 融合常数，来自信息检索实践，作用是把“排名”变成可加的分数
RRF_K = 60

_bm25_cache_lock = threading.Lock()
_bm25_cache: dict[str, object] = {}
_stats_cache: dict[str, object] = {}


def _min_coverage(default: float) -> float:
    """门槛从配置读，便于不改代码调整“保守 / 召回”的取舍。"""
    value = settings.retrieval_min_coverage
    return value if value > 0 else default


@dataclass
class RetrievalResult:
    query: str
    hits: list[SearchHit] = field(default_factory=list)
    top_score: float = 0.0
    has_context: bool = False
    reason: str = ""
    used_provider: str = ""
    threshold: float = 0.0
    methods: list[str] = field(default_factory=list)

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


def _get_bm25(docs: list[str]):
    """按索引版本缓存 BM25 语料：文档增删后版本号变化，自动重建。"""
    index = get_index()
    key = f"{id(index)}:{index.version}:{len(docs)}"
    with _bm25_cache_lock:
        cached = _bm25_cache.get(key)
        if cached is not None:
            return cached
        built = lexical.BM25Index(docs)
        # 只保留最新一份，避免缓存无限增长
        _bm25_cache.clear()
        _bm25_cache[key] = built
        return built


def _get_stats(docs: list[str]) -> lexical.CorpusStats:
    """语料统计（IDF 权重）同样按索引版本缓存，和 BM25 一个生命周期。"""
    index = get_index()
    key = f"{id(index)}:{index.version}:{len(docs)}"
    with _bm25_cache_lock:
        cached = _stats_cache.get(key)
        if cached is not None:
            return cached
        built = lexical.CorpusStats(docs)
        _stats_cache.clear()
        _stats_cache[key] = built
        return built


class Retriever:
    def __init__(
        self,
        top_k: int | None = None,
        min_score: float | None = None,
        mode: str | None = None,
    ) -> None:
        self.top_k = top_k or settings.retrieval_top_k
        # 传 None 表示使用自适应阈值；传具体数字则强制覆盖
        self.min_score = min_score if min_score is not None else None
        self.mode = (mode or settings.retrieval_mode).lower()

    def _resolve_threshold(self, provider: str) -> float:
        if self.min_score is not None:
            return self.min_score
        if settings.retrieval_min_score > 0:
            return settings.retrieval_min_score
        return AUTO_MIN_SCORE.get(provider, 0.2)

    def _vector_hits(
        self, query: str, threshold: float, provider: str, stats: lexical.CorpusStats | None
    ) -> list[SearchHit]:
        embedder = get_embedder()
        index = get_index()
        qvec = embedder.embed([query])[0]
        # 多取一些，给融合留余量
        raw = index.search(qvec, top_k=self.top_k * 2)
        is_local = provider == "local-hashing"
        min_cov = _min_coverage(LOCAL_MIN_COVERAGE)
        out: list[SearchHit] = []
        for h in raw:
            if is_local:
                # 本地哈希向量的余弦其实也只是“共享字符比例”，必须再过一道词面门槛
                cov = stats.weighted_coverage(query, h.text) if stats else 0.0
                if cov < min_cov:
                    continue
                # 词面模式下，余弦 + 覆盖度各占一半，排序更贴近“真的讲了这件事”
                score = 0.5 * h.score + 0.5 * cov
            else:
                score = h.score
            if score < threshold:
                continue
            out.append(SearchHit(h.document_id, h.file_name, h.chunk_index, h.text, score))
        return out

    def _lexical_hits(self, query: str, stats: lexical.CorpusStats) -> list[SearchHit]:
        index = get_index()
        records = index.documents()
        if not records:
            return []
        bm25 = _get_bm25([r.text for r in records])
        min_cov = _min_coverage(LEXICAL_MIN_COVERAGE)
        out: list[SearchHit] = []
        for hit in bm25.search(query, top_k=self.top_k * 2):
            rec = records[hit.index]
            cov = stats.weighted_coverage(query, rec.text)
            if cov < min_cov:
                continue
            # 展示分数用覆盖度（0~1 可解释），排序交给后面的 RRF
            out.append(
                SearchHit(rec.document_id, rec.file_name, rec.chunk_index, rec.text, cov)
            )
        return out

    def retrieve(self, query: str) -> RetrievalResult:
        query = (query or "").strip()
        if not query:
            return RetrievalResult(query=query, reason="empty_query")

        embedder = get_embedder()
        index = get_index()
        if index.size == 0:
            return RetrievalResult(
                query=query,
                reason="empty_index",
                used_provider=embedder.name,
                methods=self._planned_methods(),
            )

        threshold = self._resolve_threshold(embedder.name)
        methods = self._planned_methods()

        # 词法通道、以及本地哈希向量通道，都需要 IDF 统计来判断“这个词重不重要”
        needs_stats = "bm25" in methods or embedder.name == "local-hashing"
        try:
            stats = _get_stats([r.text for r in index.documents()]) if needs_stats else None
            vector_hits = (
                self._vector_hits(query, threshold, embedder.name, stats)
                if "vector" in methods
                else []
            )
            lexical_hits = (
                self._lexical_hits(query, stats) if "bm25" in methods and stats else []
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("检索失败")
            return RetrievalResult(
                query=query,
                reason=f"retrieval_error: {exc}",
                used_provider=embedder.name,
                threshold=threshold,
                methods=methods,
            )

        # ---- RRF 融合：按“在各自榜单里的排名”累加，避免两路分数量纲不同的问题 ----
        merged: dict[tuple[str, int], dict] = {}
        for rank, hit in enumerate(vector_hits):
            key = (hit.document_id, hit.chunk_index)
            item = merged.setdefault(key, {"hit": hit, "score": hit.score, "rrf": 0.0})
            item["rrf"] += 1.0 / (RRF_K + rank + 1)
            item["score"] = max(item["score"], hit.score)
        for rank, hit in enumerate(lexical_hits):
            key = (hit.document_id, hit.chunk_index)
            item = merged.setdefault(key, {"hit": hit, "score": hit.score, "rrf": 0.0})
            item["rrf"] += 1.0 / (RRF_K + rank + 1)
            item["score"] = max(item["score"], hit.score)

        ranked = sorted(merged.values(), key=lambda x: x["rrf"], reverse=True)

        # 片段去重：同一文档相邻片段高度重复时只保留分数最高的一个
        deduped: list[SearchHit] = []
        for item in ranked:
            h: SearchHit = item["hit"]
            if any(
                h.document_id == d.document_id and abs(h.chunk_index - d.chunk_index) <= 1
                for d in deduped
            ):
                continue
            deduped.append(SearchHit(h.document_id, h.file_name, h.chunk_index, h.text, item["score"]))
            if len(deduped) >= self.top_k:
                break

        has_ctx = bool(deduped)
        return RetrievalResult(
            query=query,
            hits=deduped,
            top_score=max((h.score for h in deduped), default=0.0),
            has_context=has_ctx,
            reason="ok" if has_ctx else "below_threshold",
            used_provider=embedder.name,
            threshold=round(threshold, 3),
            methods=methods,
        )

    def _planned_methods(self) -> list[str]:
        if self.mode == "vector":
            return ["vector"]
        if self.mode == "lexical":
            return ["bm25"]
        return ["vector", "bm25"]


def get_retriever() -> Retriever:
    return Retriever()
