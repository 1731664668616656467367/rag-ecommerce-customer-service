"""反馈接口：用户对助手回答点“有帮助 / 没帮助”。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as OrmSession

from app.db.session import get_db
from app.schemas.models import FeedbackCreate, FeedbackOut
from app.services import session_service

router = APIRouter(tags=["feedback"])


@router.post("/feedback", response_model=FeedbackOut, status_code=201)
def create_feedback(payload: FeedbackCreate, db: OrmSession = Depends(get_db)):
    try:
        fb = session_service.add_feedback(db, payload.message_id, payload.rating, payload.comment)
    except session_service.SessionNotFound as exc:
        raise HTTPException(status_code=404, detail="消息不存在") from exc
    return FeedbackOut.model_validate(fb)
