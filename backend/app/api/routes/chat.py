"""聊天接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as OrmSession

from app.db.session import get_db
from app.schemas.models import ChatRequest, ChatResponse
from app.services import chat_service, session_service

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, db: OrmSession = Depends(get_db)) -> ChatResponse:
    try:
        result = await chat_service.handle_chat(
            db, message=payload.message, session_id=payload.session_id
        )
    except chat_service.ChatInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except session_service.SessionNotFound as exc:
        raise HTTPException(status_code=404, detail="会话不存在") from exc
    return ChatResponse(**result)
