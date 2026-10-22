"""聊天接口。

两个端点：
    GET  /api/chat/welcome  首屏欢迎语 + 快捷问题（只读，不建会话）
    POST /api/chat          一次问答

为什么欢迎语要单独做成接口，而不是写死在前端？
    文案和快捷问题的 query 都必须和后端真实能力对齐（哪些问题能查到资料、
    哪些只能给能力说明）。放在后端，改文案只改一处，前端也不会出现
    “按钮上写的”和“实际提交的”不一致。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as OrmSession

from app.db.session import get_db
from app.schemas.models import ChatRequest, ChatResponse, WelcomeResponse
from app.services import chat_service, session_service

router = APIRouter(tags=["chat"])


@router.get("/chat/welcome", response_model=WelcomeResponse)
def welcome() -> WelcomeResponse:
    """首屏欢迎语。不创建会话、不写数据库，可安全重复调用。"""
    return WelcomeResponse(**chat_service.welcome_payload())


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
