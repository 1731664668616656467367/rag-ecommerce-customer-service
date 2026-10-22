"""检索门槛评估脚本：用固定样本量化“加权覆盖度”在正/负样本上的分布。

用法：
    ./.venv/Scripts/python.exe scripts/eval_retrieval.py

它跑的是当前真实索引（data/index）里的知识库。改了分块、换了 embedding、
或者往知识库补了文档之后，都应该重跑一次，看阈值还站不站得住。
"""

from __future__ import annotations

import sys

sys.path.insert(0, ".")

from app.rag import lexical
from app.rag.retriever import Retriever
from app.rag.vector_store import get_index

POSITIVE = [
    "商品有质量问题，签收后多久内可以退货？",
    "退款一般多久能到账？",
    "同城配送一般几天能到？",
    "怎么修改收货地址？",
    "优惠券可以叠加吗？",
    "保修多久",
    "发票怎么开",
    "退款",
    "发货时间",
    "订单可以取消吗",
    "怎么退货",
    "换货要多久",
    "包邮吗",
]

NEGATIVE = [
    "你们支持火星配送吗？",
    "火星探测器什么时候发射",
    "今天天气怎么样",
    "你们老板是谁",
    "股票明天会涨吗",
    "帮我写一首诗",
    "请介绍一下量子力学",
    "附近有什么好吃的",
]


def main() -> None:
    records = get_index().documents()
    if not records:
        print("索引为空，先导入知识库")
        return
    stats = lexical.CorpusStats([r.text for r in records])
    retriever = Retriever()
    print(f"语料片段数 {len(records)}，加权覆盖度门槛依赖当前语料，务必与线上一致\n")

    def probe(q: str) -> tuple[float, float, bool]:
        best = max(records, key=lambda r: lexical.coverage(q, r.text))
        raw = lexical.coverage(q, best.text)
        wt = stats.weighted_coverage(q, best.text)
        res = retriever.retrieve(q)
        return raw, wt, res.has_context

    print(f"{'raw':>6} {'weighted':>9} {'has':>4}  问题")
    print("-" * 62)
    print("正样本（期望 has=True）")
    missed = []
    for q in POSITIVE:
        raw, wt, has = probe(q)
        print(f"{raw:6.3f} {wt:9.3f} {str(has):>4}  {q}")
        if not has:
            missed.append(q)
    print("\n负样本（期望 has=False）")
    false_alarm = []
    for q in NEGATIVE:
        raw, wt, has = probe(q)
        print(f"{raw:6.3f} {wt:9.3f} {str(has):>4}  {q}")
        if has:
            false_alarm.append(q)

    print("\n结论")
    print(f"  漏答 {len(missed)}/{len(POSITIVE)}: {missed}")
    print(f"  误答 {len(false_alarm)}/{len(NEGATIVE)}: {false_alarm}")

    sweep_min_score(records)


def sweep_min_score(records) -> None:
    """语义模型下，直接量“最高余弦”在正/负样本上的分布，给出阈值建议。

    为什么单独做这一步：
        覆盖度只能在共享字词时才有值。像“今天股市怎么样”和知识库一个字都不重合，
        覆盖度是 0，但它和某段文本的余弦仍可能有 0.3~0.4——这正是语义模型
        最容易误放行的地方。只有把余弦分布打出来，才知道 RETRIEVAL_MIN_SCORE
        该定在哪里，而不是沿用词面向量时代的 0.15。
    """
    import numpy as np

    from app.rag.embeddings import get_embedder

    embedder = get_embedder()
    if embedder.name == "local-hashing":
        print("\n（当前为本地哈希向量，余弦只反映字面重合，跳过语义阈值扫描）")
        return

    texts = [r.text for r in records]
    M = embedder.embed(texts)
    Q = embedder.embed(POSITIVE + NEGATIVE)
    sims = (Q @ M.T).max(axis=1)
    pos = sorted(float(x) for x in sims[: len(POSITIVE)])
    neg = sorted(float(x) for x in sims[len(POSITIVE) :])

    print(f"\n最高余弦分布（{embedder.name} / {M.shape[1]} 维）")
    print("  正样本:", " ".join(f"{x:.3f}" for x in pos))
    print("  负样本:", " ".join(f"{x:.3f}" for x in neg))
    print(f"  正样本最低 {pos[0]:.3f} / 负样本最高 {neg[-1]:.3f}")

    if pos[0] <= neg[-1]:
        print("  两类有重叠：单靠阈值无法完全分开，需要更多同义/近义负样本再评估")
    best = max(
        (
            (
                sum(1 for x in pos if x >= t) / len(pos) + sum(1 for x in neg if x < t) / len(neg),
                t,
            )
            for t in np.arange(0.30, 0.80, 0.005)
        )
    )
    print(f"  建议 RETRIEVAL_MIN_SCORE ≈ {best[1]:.3f}（样本内召回+拒答 = {best[0]:.2f}/2）")
    print("  注意：样本很小（当前仅 5 篇文档），够用但不等于充分校准。")


if __name__ == "__main__":
    main()
