"""会话接口：列表、新建、消息历史、删除。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session as OrmSession

from app.db.session import get_db
from app.schemas.models import MessageOut, SessionCreate, SessionOut
from app.services import session_service

router = APIRouter(tags=["sessions"])


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(db: OrmSession = Depends(get_db)) -> list[SessionOut]:
    return [SessionOut.model_validate(s) for s in session_service.list_sessions(db)]


@router.post("/sessions", response_model=SessionOut, status_code=201)
def create_session(payload: SessionCreate | None = None, db: OrmSession = Depends(get_db)):
    title = payload.title if payload else None
    return SessionOut.model_validate(session_service.create_session(db, title))


@router.get("/sessions/{session_id}/messages", response_model=list[MessageOut])
def get_messages(session_id: str, db: OrmSession = Depends(get_db)):
    try:
        msgs = session_service.list_messages(db, session_id)
    except session_service.SessionNotFound as exc:
        raise HTTPException(status_code=404, detail="会话不存在") from exc
    return [MessageOut.model_validate(m) for m in msgs]


@router.delete("/sessions/{session_id}", status_code=204, response_class=Response)
def delete_session(session_id: str, db: OrmSession = Depends(get_db)) -> Response:
    try:
        session_service.delete_session(db, session_id)
    except session_service.SessionNotFound as exc:
        raise HTTPException(status_code=404, detail="会话不存在") from exc
    return Response(status_code=204)
