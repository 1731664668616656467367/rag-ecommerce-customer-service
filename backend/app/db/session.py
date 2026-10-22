"""数据库连接与会话管理。

SQLite 默认不检查外键，这里通过 PRAGMA 打开，
否则 ondelete="CASCADE" 只是写在纸上，删会话时消息会变成孤儿数据。
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import logging

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db.models import Base

logger = logging.getLogger(__name__)

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


# 轻量迁移：create_all 不会给已存在的表加新列，
# 所以新增字段要在这里显式补一次（SQLite 支持 ADD COLUMN，且不动已有数据）。
_ADDED_COLUMNS: list[tuple[str, str, str]] = [
    ("messages", "answer_mode", "VARCHAR(24)"),
    ("messages", "reply_type", "VARCHAR(24)"),
]


def _run_light_migrations(engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as conn:
        for table, column, ddl_type in _ADDED_COLUMNS:
            rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
            existing = {row[1] for row in rows}
            if not existing:
                continue  # 表还没建出来，交给 create_all
            if column not in existing:
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")
                logger.info("数据库迁移：%s 表新增列 %s", table, column)


def init_db() -> None:
    """建表 + 轻量迁移。已存在的表和数据不会被破坏，可重复调用。"""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _run_light_migrations(engine)


def get_db() -> Iterator[OrmSession]:
    """FastAPI 依赖：每个请求一个会话，用完自动关闭。"""
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
