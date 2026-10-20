"""Pydantic 请求/响应模型。

作用不只是“类型标注”：FastAPI 会用它们自动做参数校验（422）、
生成 OpenAPI 文档，并过滤掉多余字段，避免脏数据进入业务层。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------- 通用 ----------------
class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    app: str
    env: str
    version: str
    database: str
    embedding: dict
    llm: dict
    index: dict
    warnings: list[str] = []


class ErrorResponse(BaseModel):
    detail: str
    code: str = "error"


# ---------------- 会话 ----------------
class SessionCreate(BaseModel):
    title: str | None = Field(default=None, max_length=120)


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class SourceOut(BaseModel):
    document_id: str
    file_name: str
    chunk_index: int
    score: float
    snippet: str = ""


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    role: Literal["user", "assistant"]
    content: str
    intent: str | None = None
    sources: list[SourceOut] | None = None
    degraded: str | None = None
    created_at: datetime


# ---------------- 聊天 ----------------
class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, max_length=32)

    @field_validator("message")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("消息不能为空白")
        return v.strip()


class ChatResponse(BaseModel):
    session_id: str
    session_title: str
    message_id: str
    answer: str
    intent: str
    intent_method: str
    sources: list[SourceOut] = []
    degraded: str | None = None
    retrieval: dict


# ---------------- 知识库 ----------------
class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    file_name: str
    file_type: str
    size_bytes: int
    status: Literal["pending", "indexed", "failed"]
    chunk_count: int
    index_version: str
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class KnowledgeListResponse(BaseModel):
    documents: list[DocumentOut]
    index: dict


# ---------------- 反馈 ----------------
class FeedbackCreate(BaseModel):
    message_id: str = Field(min_length=4, max_length=32)
    rating: Literal["helpful", "unhelpful"]
    comment: str | None = Field(default=None, max_length=500)


class FeedbackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    message_id: str
    rating: str
    comment: str | None = None
    created_at: datetime
