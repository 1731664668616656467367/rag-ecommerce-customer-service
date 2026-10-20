"""RAG 链路测试：分块、入库、检索命中、无结果、删除隔离。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app.rag.chunker import chunk_text, clean_text
from app.rag.embeddings import LocalHashingEmbedder, get_embedder
from app.rag.retriever import Retriever
from app.rag.vector_store import VectorIndex, get_index


def test_clean_text_collapses_whitespace():
    raw = "第一行  \r\n\r\n\r\n  第二行\u00a0内容"
    assert clean_text(raw) == "第一行\n\n第二行 内容"


def test_chunk_text_splits_and_overlaps():
    text = "。".join([f"这是第{i}条说明内容，用于测试分块逻辑是否正常工作" for i in range(40)]) + "。"
    chunks = chunk_text(text, chunk_size=120, overlap=20)
    assert len(chunks) > 3
    assert all(len(c) <= 200 for c in chunks)
    # 不允许整段丢失：所有块的字符总量应大于原文的 80%
    assert sum(len(c) for c in chunks) > len(text) * 0.8


def test_chunk_text_empty():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_local_embedding_is_normalized_and_deterministic():
    emb = LocalHashingEmbedder(dim=256)
    a = emb.embed(["退款需要几天到账", "退款需要几天到账"])
    assert a.shape == (2, 256)
    assert np.allclose(np.linalg.norm(a, axis=1), 1.0)
    assert np.allclose(a[0], a[1])


def test_similar_text_scores_higher_than_unrelated():
    emb = get_embedder()
    vecs = emb.embed(["退款几天到账", "退款到账时间是几天", "会员积分怎么兑换"])
    sim_related = float(vecs[0] @ vecs[1])
    sim_unrelated = float(vecs[0] @ vecs[2])
    assert sim_related > sim_unrelated


def test_index_upsert_and_search(indexed_doc):
    index = get_index()
    assert index.size > 0
    retriever = Retriever(top_k=3, min_score=0.05)
    result = retriever.retrieve("退款多久能到账")
    assert result.has_context is True
    assert result.hits
    assert result.hits[0].file_name == "退换货政策.md"
    assert any("退" in h.text for h in result.hits)


def test_retrieval_without_relevant_docs(client, indexed_doc):
    """知识库有内容但问题完全无关时，必须判定无相关资料。"""
    retriever = Retriever(top_k=3, min_score=0.6)
    result = retriever.retrieve("火星探测器什么时候发射")
    assert result.has_context is False
    assert result.reason == "below_threshold"
    assert result.sources() == []


def test_retrieval_on_empty_index(client):
    result = Retriever().retrieve("退款多久到账")
    assert result.has_context is False
    assert result.reason == "empty_index"


def test_delete_one_document_keeps_others(db, sample_text):
    from app.services import knowledge_service

    d1 = knowledge_service.add_document(db, "政策A.md", sample_text.encode("utf-8"))
    d2 = knowledge_service.add_document(db, "政策B.md", "物流时效说明：同城次日达，跨省三到五天。".encode("utf-8"))
    index = get_index()
    total_before = index.size

    knowledge_service.delete_document(db, d1.id)

    remaining = [r.document_id for r in index._records]
    assert d1.id not in remaining
    assert d2.id in remaining
    assert index.size == total_before - d1.chunk_count

    # 删完后仍能检索到另一份文档
    result = Retriever(top_k=3, min_score=0.05).retrieve("同城多久能到")
    assert any(h.document_id == d2.id for h in result.hits)


def test_reupload_same_filename_replaces_vectors(db):
    from app.services import knowledge_service

    doc1 = knowledge_service.add_document(db, "同名.md", "第一版内容：退款三个工作日到账。".encode("utf-8"))
    size1 = get_index().size
    doc2 = knowledge_service.add_document(db, "同名.md", "第二版内容：退款五个工作日到账。".encode("utf-8"))
    assert doc1.id != doc2.id
    assert get_index().size == size1  # 不是叠加，是替换
    assert all(r.document_id != doc1.id for r in get_index()._records)


def test_vector_index_persistence(tmp_path: Path):
    idx = VectorIndex(index_dir=tmp_path)
    emb = LocalHashingEmbedder(dim=64)
    texts = ["退款需要三个工作日", "物流同城次日达"]
    idx.upsert_document("doc-1", "a.md", texts, emb.embed(texts))

    reloaded = VectorIndex(index_dir=tmp_path)
    assert reloaded.size == 2
    hits = reloaded.search(emb.embed(["退款多久"])[0], top_k=1)
    assert hits and hits[0].document_id == "doc-1"


def test_vector_index_dimension_mismatch(tmp_path: Path):
    idx = VectorIndex(index_dir=tmp_path)
    idx.upsert_document("doc-1", "a.md", ["退款"], LocalHashingEmbedder(dim=32).embed(["退款"]))
    with pytest.raises(ValueError):
        idx.upsert_document("doc-2", "b.md", ["物流"], LocalHashingEmbedder(dim=64).embed(["物流"]))
