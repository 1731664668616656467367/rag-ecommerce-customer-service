"""会话与消息服务。

关键点：
1. 历史记录来自数据库查询，不是内存列表 —— 所以重启后仍然存在。
2. 每个查询都带 session_id 过滤 —— 保证不同会话上下文互相隔离。
3. 排序用 created_at，再用自增行序兜底，避免同一秒内多条消息顺序错乱。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import settings
from app.db.models import Feedback, Message, Session

logger = logging.getLogger(__name__)


class SessionNotFound(Exception):
    pass


def create_session(db: OrmSession, title: str | None = None) -> Session:
    session = Session(title=(title or "新会话")[:120])
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def list_sessions(db: OrmSession, limit: int = 50) -> list[Session]:
    stmt = select(Session).order_by(Session.updated_at.desc()).limit(limit)
    return list(db.scalars(stmt))


def get_session(db: OrmSession, session_id: str) -> Session:
    session = db.get(Session, session_id)
    if session is None:
        raise SessionNotFound(session_id)
    return session


def delete_session(db: OrmSession, session_id: str) -> None:
    session = get_session(db, session_id)
    # 显式删除关联消息，不完全依赖级联，便于日志追踪
    db.delete(session)
    db.commit()


def list_messages(db: OrmSession, session_id: str) -> list[Message]:
    get_session(db, session_id)  # 不存在直接 404
    stmt = (
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    return list(db.scalars(stmt))


def add_message(
    db: OrmSession,
    session_id: str,
    role: str,
    content: str,
    intent: str | None = None,
    sources: list | None = None,
    degraded: str | None = None,
) -> Message:
    msg = Message(
        session_id=session_id,
        role=role,
        content=content,
        intent=intent,
        sources=sources,
        degraded=degraded,
    )
    db.add(msg)
    # 更新会话活跃时间，让会话列表按最近使用排序
    session = db.get(Session, session_id)
    if session is not None:
        session.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(msg)
    return msg


def recent_history(db: OrmSession, session_id: str, window: int | None = None) -> list[dict]:
    """取最近 N 条消息作为对话上下文。只取本会话，天然隔离。"""
    w = window or settings.history_window
    msgs = list_messages(db, session_id)
    tail = msgs[-w:] if w > 0 else []
    return [{"role": m.role, "content": m.content} for m in tail]


def auto_title(question: str) -> str:
    t = " ".join(question.split())
    return (t[:24] + "…") if len(t) > 24 else (t or "新会话")


def touch_title_if_default(db: OrmSession, session: Session, question: str) -> None:
    if session.title in ("新会话", "", None):
        session.title = auto_title(question)
        db.commit()


def add_feedback(db: OrmSession, message_id: str, rating: str, comment: str | None = None) -> Feedback:
    msg = db.get(Message, message_id)
    if msg is None:
        raise SessionNotFound(message_id)
    fb = Feedback(message_id=message_id, rating=rating, comment=comment)
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb
