"""本地词法检索（BM25）。

为什么要加它：
    没有 Ollama 时，向量是“字符哈希”算出来的，本质仍是词面匹配，而且长文档会被稀释。
    BM25 是信息检索里最经典的词法算法，两个好处：
      1. IDF 权重——“退款”这种区分度高的词权重高，“我们”“可以”这种到处都有的词权重低；
      2. 长度归一化——长片段不会因为“词多”就天然占优。

中文没有空格，这里用「字符二元组」当词（“退款”“款几”“几天”…），
外文/数字按单词切。这不需要任何分词库，也不花钱，是这个场景下最实用的近似。

注意：BM25 不懂同义词。问“东西坏了”匹配不到“质量问题”。
它和向量检索是互补的，所以默认用 hybrid 融合两路结果。
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

_ASCII_WORD = re.compile(r"[a-zA-Z0-9_]+")
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
_NON_WORD = re.compile(r"[^\u4e00-\u9fffa-z0-9]")


def tokenize(text: str) -> list[str]:
    """中文按字符 bigram，英文/数字按词；单字中文保留一元。"""
    text = (text or "").lower()
    tokens: list[str] = []
    for w in _ASCII_WORD.findall(text):
        tokens.append(w)
    for run in _CJK_RUN.findall(text):
        if len(run) == 1:
            tokens.append(run)
            continue
        for i in range(len(run) - 1):
            tokens.append(run[i : i + 2])
    return tokens


def bigrams(text: str) -> set[str]:
    """用于“词面覆盖度”的字符二元组集合（去标点、去空格）。"""
    t = _NON_WORD.sub("", (text or "").lower())
    if len(t) < 2:
        return {t} if t else set()
    return {t[i : i + 2] for i in range(len(t) - 1)}


def coverage(query: str, text: str) -> float:
    """问题里的二元组有多大比例出现在片段里，范围 0~1。

    这是“原始覆盖度”：每个二元组等权。它有两个已知的缺陷：
      1. “我们”“可以”这种到处都有的词，和“发票”这种关键术语权重一样；
      2. 问句里的切词碎片（“款一”“天能”这种跨词边界的二元组）几乎不可能命中，
         却和真正的关键词一样占分母，导致短问句天然低分。
    所以真正做判定时用的是下面的 weighted_coverage。
    """
    q = bigrams(query)
    if not q:
        return 0.0
    return len(q & bigrams(text)) / len(q)


class CorpusStats:
    """语料统计：判断“问题里的词有多重要、有多少真的出现在片段里”。

    为什么需要它：
        等权覆盖度分不清这两句话——
            「你们支持火星配送吗？」（不该命中）
            「换货要多久？」（该命中）
        两者都是“少量二元组命中”，比例甚至一样。真正的差别是：
        前者的关键词「火星」在语料里根本不存在，后者命中的「换货」是实打实的话题词。

    权重怎么算：
        w = 1 / (1 + 文档频率)。一个词出现在越多片段里越不重要，
        语料里从没出现过的词（df=0）权重最高，等于 1.0。

    为什么不用标准 IDF：
        IDF 的绝对值依赖语料规模。只有 1 个片段时，所有词的 IDF 都一样，
        未登录词只是它们的 4.8 倍；语料涨到 200 段时这个比例又掉到 1.26 倍。
        同一个阈值放在小知识库上严、放在大知识库上松，这种漂移会让门槛
        变成一个说不清的东西。1/(1+df) 的比例是恒定的（未登录词永远是
        已出现 1 次词的 2 倍），所以阈值在 1 段和 200 段语料上是同一把尺子。
    """

    def __init__(self, docs: list[str]) -> None:
        self.n = len(docs)
        df: Counter[str] = Counter()
        for d in docs:
            for bg in bigrams(d):
                df[bg] += 1
        self._df = df

    def term_weight(self, term: str) -> float:
        return 1.0 / (1.0 + self._df.get(term, 0))

    def weighted_coverage(self, query: str, text: str) -> float:
        """按词的区分度加权后，问题有多少“分量”落在片段里，范围 0~1。"""
        q = bigrams(query)
        if not q:
            return 0.0
        tb = bigrams(text)
        total = sum(self.term_weight(bg) for bg in q)
        if total <= 0:
            return 0.0
        got = sum(self.term_weight(bg) for bg in q & tb)
        return got / total


@dataclass
class LexicalHit:
    index: int      # 对应传入文档列表的下标
    score: float    # 归一化后的分数（本次查询最高分为 1.0）


class BM25Index:
    """轻量 BM25，语料是当前向量索引里的所有片段。"""

    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._docs_tokens = [tokenize(d) for d in docs]
        self._doc_len = [len(t) for t in self._docs_tokens]
        self._avg_len = (sum(self._doc_len) / len(self._doc_len)) if self._doc_len else 0.0
        self._freqs = [Counter(t) for t in self._docs_tokens]

        # 文档频率 -> IDF
        df: Counter[str] = Counter()
        for tok in self._docs_tokens:
            for term in set(tok):
                df[term] += 1
        n = len(self._docs_tokens)
        self._idf = {
            term: math.log(1 + (n - freq + 0.5) / (freq + 0.5)) for term, freq in df.items()
        }

    def search(self, query: str, top_k: int = 10) -> list[LexicalHit]:
        terms = tokenize(query)
        if not terms or not self._docs_tokens:
            return []
        scores: list[float] = []
        for i, freq in enumerate(self._freqs):
            s = 0.0
            dl = self._doc_len[i] or 1
            for term in terms:
                f = freq.get(term)
                if not f:
                    continue
                idf = self._idf.get(term, 0.0)
                denom = f + self.k1 * (1 - self.b + self.b * dl / (self._avg_len or 1))
                s += idf * (f * (self.k1 + 1)) / denom
            scores.append(s)

        ranked = sorted(
            ((i, s) for i, s in enumerate(scores) if s > 0), key=lambda x: -x[1]
        )[:top_k]
        if not ranked:
            return []
        top = ranked[0][1] or 1.0
        return [LexicalHit(index=i, score=s / top) for i, s in ranked]
