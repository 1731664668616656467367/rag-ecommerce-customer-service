"""健康检查。

不撒谎是关键：
- 纯知识库模式是**正常模式**，不因为“没配密钥”而报降级；
- 但如果 embedding 降级、索引为空、索引与当前模型不匹配，必须明确告警；
- 明确告诉调用方“当前回答来自哪里”，前端设置页直接展示。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session as OrmSession

from app.config import settings
from app.db.session import get_db
from app.rag.embeddings import embedding_status, get_embedder
from app.rag.retriever import get_retriever
from app.rag.vector_store import get_index
from app.runtime_mode import (
    current_override,
    effective_answer_mode,
    effective_llm_enabled,
    effective_llm_ready,
)
from app.schemas.models import HealthResponse

router = APIRouter(tags=["health"])

VERSION = "1.0.0"


@router.get("/health", response_model=HealthResponse)
def health(db: OrmSession = Depends(get_db)) -> HealthResponse:
    warnings: list[str] = []

    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception as exc:  # noqa: BLE001
        database = f"error: {type(exc).__name__}"
        warnings.append("数据库不可用")

    # ---------- 检索能力 ----------
    embedder = get_embedder()
    # embedding_status 会带上“配置要求 / 实际生效 / 回退原因”，
    # 状态页据此说明为什么不是 Ollama，而不是只显示一句“未连接”。
    emb_health = embedding_status()
    if embedder.name != "ollama":
        reason = emb_health.get("fallback_reason") or "未探测到可用的 Ollama"
        configured = emb_health.get("configured_provider")
        if configured == "ollama":
            warnings.append(
                f"EMBEDDING_PROVIDER=ollama，但 Ollama 不可用：{reason}。"
                "当前已降级为本地哈希向量 + BM25，知识库仍可使用（重启后端会重新探测）"
            )
        else:
            warnings.append(
                f"当前使用本地哈希向量（EMBEDDING_PROVIDER={configured}）：{reason}。"
                "只能做词面近似匹配，不等同于语义检索；已启用 BM25 词法检索作为补充"
            )

    index_stats = get_index().stats()
    current_sig = embedder.signature()
    stored_sig = index_stats.get("signature") or ""
    needs_reindex = bool(stored_sig and stored_sig != current_sig)
    if needs_reindex:
        warnings.append(
            f"索引由 {stored_sig} 建立，当前 embedding 为 {current_sig}，请调用 "
            "/api/knowledge/reindex 重建索引"
        )
    if index_stats["chunks"] == 0:
        warnings.append("知识库索引为空，请先上传文档")

    retrieval_detail = {
        "mode": settings.retrieval_mode,
        "channels": get_retriever()._planned_methods(),
        "vector_backend": index_stats.get("backend", "numpy"),
        "embedding_signature": current_sig,
        "index_signature": stored_sig,
        "needs_reindex": needs_reindex,
        # 设置页要展示"检索设置"就得有真实数字，不能让前端猜默认值
        "top_k": settings.retrieval_top_k,
        "min_score": settings.retrieval_min_score,
        "min_coverage": settings.retrieval_min_coverage,
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
        "embedding_provider": embedder.name,
        "embedding_model": emb_health.get("model"),
    }

    # ---------- 回答来源 ----------
    # 报告的是**当前生效**的模式（用户在页面上切换过的），不是 .env 的静态值。
    # source 字段说明这个值从哪来，避免“为什么和 .env 不一致”的困惑。
    mode = effective_answer_mode()
    llm_detail = {
        "provider": "deepseek",
        "model": settings.deepseek_model,
        "mode": mode,
        "source": "runtime" if current_override() else "env",
        "enabled": effective_llm_enabled(),
        "configured": settings.llm_configured,
        # 唯一能说明“会不会真的发出请求”的字段
        "will_be_called": effective_llm_ready(),
        "note": (
            "知识库模式：不调用任何外部模型"
            if not effective_llm_enabled()
            else ("大语言模型模式：已配置密钥" if settings.llm_configured else "大语言模型模式：缺少密钥")
        ),
    }
    if effective_llm_enabled() and not settings.llm_configured:
        warnings.append("已切换到 llm 模式，但未配置 DEEPSEEK_API_KEY，回答将退回知识库原文")

    # 纯知识库模式下，没有密钥不算问题
    llm_ok = effective_llm_ready() if effective_llm_enabled() else True
    status = "ok" if database == "ok" and llm_ok else "degraded"

    return HealthResponse(
        status=status,
        app=settings.app_name,
        env=settings.app_env,
        version=VERSION,
        answer_mode=mode,
        database=database,
        embedding=emb_health,
        retrieval=retrieval_detail,
        llm=llm_detail,
        index=index_stats,
        warnings=warnings,
    )
