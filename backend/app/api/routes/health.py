"""健康检查。

不撒谎是关键：没有 key 就报 degraded，Ollama 连不上就说明已降级。
前端会把这些 warning 原样展示，让使用者一眼看清系统真实状态。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session as OrmSession

from app.config import settings
from app.db.session import get_db
from app.rag.embeddings import get_embedder
from app.rag.vector_store import get_index
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

    embedder = get_embedder()
    emb_health = embedder.health()
    if embedder.name != "ollama":
        warnings.append(
            "未连接 Ollama，当前使用本地哈希向量（检索效果弱于 bge-m3，可在 .env 配置 EMBEDDING_PROVIDER）"
        )

    llm_detail = {
        "provider": "deepseek",
        "model": settings.deepseek_model,
        "configured": settings.llm_configured,
    }
    if not settings.llm_configured:
        warnings.append("未配置 DEEPSEEK_API_KEY，聊天将使用「仅检索降级模式」")

    index_stats = get_index().stats()
    if index_stats["chunks"] == 0:
        warnings.append("知识库索引为空，请先上传文档")

    status = "ok" if database == "ok" and settings.llm_configured else "degraded"
    return HealthResponse(
        status=status,
        app=settings.app_name,
        env=settings.app_env,
        version=VERSION,
        database=database,
        embedding=emb_health,
        llm=llm_detail,
        index=index_stats,
        warnings=warnings,
    )
