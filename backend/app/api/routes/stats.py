"""工作台统计接口。

设计原则：**只报数据库里真有的东西**。
- 会话数、消息数、今日消息、文档数、片段数、回答类型分布、降级次数，
  全部来自 SQLite 聚合查询；
- 没有埋点的指标（例如"检索命中率"如果要按请求统计就需要日志表）不做，
  页面显示"暂无数据"，而不是编一个好看的百分比。

"今日"按**服务器本地时区**切分：数据库存的是 UTC，直接按 UTC 切会让
UTC+8 的用户在早上 8 点前看到"今日 0 条"。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.db.models import Feedback, KnowledgeDocument, Message, Session
from app.db.session import get_db
from app.rag.vector_store import get_index
from app.schemas.models import StatsResponse
from app.services import settings_service
from app.runtime_mode import effective_answer_mode

router = APIRouter(tags=["stats"])


def _local_day_bounds_utc() -> tuple[datetime, datetime]:
    """把"本地今天"换算成 UTC 的 [start, end)，用于和时间戳列比较。"""
    now_local = datetime.now().astimezone()
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    to_utc = lambda d: d.astimezone(timezone.utc).replace(tzinfo=None)  # noqa: E731
    return to_utc(start_local), to_utc(end_local)


@router.get("/stats", response_model=StatsResponse)
def stats(db: OrmSession = Depends(get_db)) -> StatsResponse:
    day_start, day_end = _local_day_bounds_utc()

    sessions_total = db.scalar(select(func.count()).select_from(Session)) or 0
    sessions_today = (
        db.scalar(
            select(func.count()).select_from(Session).where(
                Session.created_at >= day_start, Session.created_at < day_end
            )
        )
        or 0
    )

    messages_total = db.scalar(select(func.count()).select_from(Message)) or 0
    messages_today = (
        db.scalar(
            select(func.count()).select_from(Message).where(
                Message.created_at >= day_start, Message.created_at < day_end
            )
        )
        or 0
    )

    assistant_total = (
        db.scalar(select(func.count()).select_from(Message).where(Message.role == "assistant")) or 0
    )

    # 回答类型分布：回答"这些回复是谁产生的"，用于知识引用率而非营销数字
    rows = db.execute(
        select(Message.reply_type, func.count())
        .where(Message.role == "assistant")
        .group_by(Message.reply_type)
    ).all()
    answer_mix = {(k or "unknown"): v for k, v in rows}

    degraded_total = (
        db.scalar(
            select(func.count()).select_from(Message).where(Message.degraded.is_not(None))
        )
        or 0
    )

    docs_total = db.scalar(select(func.count()).select_from(KnowledgeDocument)) or 0
    docs_indexed = (
        db.scalar(
            select(func.count())
            .select_from(KnowledgeDocument)
            .where(KnowledgeDocument.status == "indexed")
        )
        or 0
    )

    helpful = db.scalar(select(func.count()).select_from(Feedback).where(Feedback.rating == "helpful")) or 0
    unhelpful = (
        db.scalar(select(func.count()).select_from(Feedback).where(Feedback.rating == "unhelpful")) or 0
    )

    index_stats = get_index().stats()
    knowledge_count = answer_mix.get("knowledge", 0)

    return StatsResponse(
        sessions_total=sessions_total,
        sessions_today=sessions_today,
        messages_total=messages_total,
        messages_today=messages_today,
        assistant_total=assistant_total,
        docs_total=docs_total,
        docs_indexed=docs_indexed,
        chunks=index_stats.get("chunks", 0),
        dim=index_stats.get("dim", 0),
        index_backend=index_stats.get("backend", "numpy"),
        answer_mix=answer_mix,
        # 有分母才给比率，否则 None（前端显示"—"），不拿 0 条当 0%
        knowledge_ratio=(knowledge_count / assistant_total) if assistant_total else None,
        degraded_total=degraded_total,
        feedback_helpful=helpful,
        feedback_unhelpful=unhelpful,
        answer_mode=effective_answer_mode(),
        mode_label=settings_service.MODE_LABELS.get(effective_answer_mode(), effective_answer_mode()),
        generated_at=datetime.now(timezone.utc),
    )
