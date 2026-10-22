"""纯知识库模式的回答构造。

原则：**只摘录，不改写**。
    这里不做任何“润色”“总结”“推断”，因为一旦改写，就可能把“1 至 3 个工作日”
    写成“3 天左右”，把“需提供故障照片”漏掉——这类偏差在退款、售后场景是事故。
    所以直接把知识片段按相关度排序后原样呈现，并标注来源段落。

去重：
    相邻片段本身有 60 字重叠，且同一份文档不同段落可能重复表述。
    用字符二元组的 Jaccard 相似度判断，过像的就不重复展示。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import settings
from app.rag.lexical import bigrams
from app.rag.retriever import RetrievalResult

NO_KB_ANSWER = "暂未在知识库中找到足够可靠的信息，建议联系人工客服进一步确认。"

# 这些意图涉及具体业务承诺，只允许展示原文，不允许任何推断
HIGH_RISK_INTENTS = frozenset({"退款", "售后", "物流", "查订单"})

_HEADING = re.compile(r"#{1,6}\s*")
# 小标题单独一行、并且加粗：摘录里最容易被忽略的恰恰是"这一节讲什么"。
# 只改样式不改文字，所以"未作改写"这条承诺仍然成立。
_HEADING_LINE = re.compile(r"^#{1,6}[ \t]*(.+)$", re.M)
_LIST_MARK = re.compile(r"^\s*\d+[.、)]\s*", re.M)


def plain_text(text: str, limit: int = 300) -> str:
    """去掉 Markdown 记号，保留句子完整性，超长则在句末截断。

    为什么保留换行、不压成一行：
        知识库文档是用 "## 发货时间" 这类小节组织信息的。压成一行之后，
        小节标题会变成句子里莫名其妙的几个字（"配送与物流时效 发货时间 现货商品…"），
        用户读起来像乱码。这里让标题与段落各占一行，交给前端逐行渲染。
    """
    s = _HEADING_LINE.sub(lambda m: f"**{m.group(1).strip()}**", text)
    s = _HEADING.sub("", s)
    s = _LIST_MARK.sub("", s)
    s = re.sub(r"[ \t]*\n[ \t]*", "\n", s)
    s = re.sub(r"\n{2,}", "\n", s)
    s = re.sub(r"[ \t]{2,}", " ", s).strip()
    if len(s) <= limit:
        return s
    cut = s[:limit]
    # 尽量在标点处断开，避免半句话
    for mark in ("。", "；", "！", "？", "，", "\n", " "):
        pos = cut.rfind(mark)
        if pos >= limit * 0.6:
            return cut[: pos + 1].rstrip() + ("…" if mark not in "。！？" else "")
    return cut.rstrip() + "…"


def _too_similar(a: str, b: str, threshold: float = 0.75) -> bool:
    ga, gb = bigrams(a), bigrams(b)
    if not ga or not gb:
        return False
    inter = len(ga & gb)
    union = len(ga | gb)
    return union > 0 and inter / union >= threshold


@dataclass
class KnowledgeAnswer:
    text: str
    used_hits: int
    kind: str = "knowledge_extract"  # 便于前端/日志区分“原文摘录”与“模型生成”
    reliable: bool = False


def build_knowledge_answer(
    retrieval: RetrievalResult,
    intent: str,
    max_chunks: int | None = None,
    snippet_chars: int | None = None,
) -> KnowledgeAnswer:
    if not retrieval.has_context or not retrieval.hits:
        # kind 必须跟着内容走：没有摘录就不能标成“知识库原文”，
        # 否则前端会把一句固定提示渲染成“知识库原文”标签。
        return KnowledgeAnswer(text=NO_KB_ANSWER, used_hits=0, kind="no_answer", reliable=False)

    limit = max_chunks or settings.knowledge_answer_max_chunks
    chars = snippet_chars or settings.knowledge_answer_snippet_chars

    # 按相关度排序后再去重（检索结果已排序，这里显式做一次，避免上层改动破坏前提）
    ordered = sorted(retrieval.hits, key=lambda h: h.score, reverse=True)

    picked = []
    for h in ordered:
        if any(_too_similar(h.text, p.text) for p in picked):
            continue
        picked.append(h)
        if len(picked) >= limit:
            break

    head = "根据知识库中的相关说明，整理如下（以下为原文摘录，未作改写）："
    blocks = []
    for i, h in enumerate(picked, start=1):
        body = plain_text(h.text, chars)
        # 每个片段先标来源、再逐行引用原文：
        # 用户能一眼看到"这段来自哪份文档的第几段"，而不是先读一大段再翻到底部找出处。
        # 引用用 Markdown 的 "> " 表示，前端会渲染成带左边线的引用块。
        quoted = "\n".join(f"> {line}" for line in body.splitlines() if line.strip())
        blocks.append(f"**{i}. 《{h.file_name}》· 第 {h.chunk_index + 1} 段**\n{quoted}")

    tail = "以上内容摘自知识库文档，未做改写。具体业务办理请联系人工客服。"
    text = "\n\n".join([head, "\n\n".join(blocks), tail])
    return KnowledgeAnswer(text=text, used_hits=len(picked), reliable=True)
