"""文本清洗与分块。

为什么要分块（chunking）？
    大模型和向量检索都不适合一次吞下整篇文档：一是超长，二是检索会变“糊”——
    一篇 5000 字的文档只有一个向量，问题问的是其中一句话，相似度就被稀释了。
    所以要切成 200~400 字的小块，每块单独算向量，检索时只取最相关的几块。

切法要点：
    1. 先按段落/句子边界切，绝不把一句话从中间劈开（否则语义断裂）。
    2. 相邻块之间保留一点重叠（overlap），避免答案刚好卡在两块交界处。
    3. 记录 chunk_index，方便前端展示“来自第几段”。
"""

from __future__ import annotations

import re

from app.config import settings

# 中文句末标点 + 英文句末标点
_SENTENCE_END = re.compile(r"(?<=[。！？!?；;\n])")
_WHITESPACE = re.compile(r"[ \t\u3000]+")


def clean_text(raw: str) -> str:
    """去掉不可见字符、压缩空白、统一换行。保留中文标点与段落结构。"""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ").replace("\ufeff", "")
    # 去掉除换行外的控制字符
    text = "".join(ch for ch in text if ch == "\n" or ch >= " " or ch == "\t")
    text = _WHITESPACE.sub(" ", text)
    # 逐行去空白，但保留空行：空行是段落边界，删掉会把两段话粘成一段
    lines = [ln.strip() for ln in text.split("\n")]
    text = "\n".join(lines)
    # 连续空行压缩成一个空行，保留段落结构
    text = re.sub(r"\n{2,}", "\n\n", text)
    return text.strip()


def split_sentences(text: str) -> list[str]:
    """按句末标点切句，**保留句尾的换行**。

    为什么不能直接 `p.strip()`：
        段落之间是空行，空行会被切成只含 "\\n" 的片段。整段 strip 之后
        这个片段变成空串被丢掉，于是 "## 发货时间\\n\\n现货商品…" 会拼成
        "## 发货时间现货商品…"——标题和正文粘在一起，
        最后用户在回答里看到的就是一句没有断行的长串。
        这里只去掉空格与全角空格，换行留着当结构信息。
    """
    parts = _SENTENCE_END.split(text)
    return [p.strip(" \t\u3000") for p in parts if p.strip()]


def chunk_text(
    text: str,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[str]:
    """按句子聚合成分块，块长接近 chunk_size，相邻块尾部重叠 overlap 个字符。"""
    size = chunk_size or settings.chunk_size
    ov = overlap if overlap is not None else settings.chunk_overlap
    ov = max(0, min(ov, size // 2))

    text = clean_text(text)
    if not text:
        return []

    sentences = split_sentences(text)
    chunks: list[str] = []
    buf = ""

    for sent in sentences:
        # 单句超长（比如没有标点的长表格行）就硬切，保证不产生超大块
        while len(sent) > size:
            if buf:
                chunks.append(buf)
                buf = ""
            chunks.append(sent[:size])
            sent = sent[size - ov :] if ov else sent[size:]

        # 标题要独占一行，否则拼接后会变成“政策## 七天无理由退货”，
        # 既破坏可读性，也让 Markdown 结构丢失
        if sent.lstrip().startswith("#") and buf and not buf.endswith("\n"):
            buf += "\n"

        if len(buf) + len(sent) <= size:
            buf += sent
        else:
            if buf.strip():
                chunks.append(buf.strip())
            # 下一块以当前块的尾部作为重叠起点
            tail = buf[-ov:] if ov and buf else ""
            buf = tail + sent

    if buf.strip():
        chunks.append(buf.strip())

    # 去重（重叠可能造成完全重复的短块）
    seen: set[str] = set()
    result: list[str] = []
    for c in chunks:
        c = c.strip()
        if len(c) < 8 or c in seen:
            continue
        seen.add(c)
        result.append(c)
    return result
