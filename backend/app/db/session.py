"""数据库连接与会话管理。

SQLite 默认不检查外键，这里通过 PRAGMA 打开，
否则 ondelete="CASCADE" 只是写在纸上，删会话时消息会变成孤儿数据。
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db.models import Base

_engine = None
_SessionLocal = None


def _ensure_sqlite_dir(url: str) -> None:
    if url.startswith("sqlite:///"):
        raw = url.replace("sqlite:///", "", 1)
        Path(raw).parent.mkdir(parents=True, exist_ok=True)


def build_engine(url: str | None = None) -> Engine:
    target = url or settings.database_url
    _ensure_sqlite_dir(target)
    connect_args = {"check_same_thread": False} if target.startswith("sqlite") else {}
    eng = create_engine(target, connect_args=connect_args, future=True)

    if target.startswith("sqlite"):

        @event.listens_for(eng, "connect")
        def _set_fk(dbapi_conn, _rec):  # pragma: no cover - 纯副作用
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return eng


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = build_engine()
    return _engine


def get_session_factory() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _SessionLocal


def init_db() -> None:
    """建表。已存在的表不会被破坏，可重复调用。"""
    Base.metadata.create_all(bind=get_engine())


def get_db() -> Iterator[OrmSession]:
    """FastAPI 依赖：每个请求一个会话，用完自动关闭。"""
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
