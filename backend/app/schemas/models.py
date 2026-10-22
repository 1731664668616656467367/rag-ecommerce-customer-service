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
    answer_mode: Literal["knowledge_only", "llm"]
    database: str
    embedding: dict
    retrieval: dict
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
    answer_mode: str | None = None
    reply_type: str | None = None
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


class SuggestionOut(BaseModel):
    """快捷问题。query 是点击后真正提交给 /api/chat 的内容。"""

    label: str = Field(max_length=40)
    query: str = Field(max_length=200)
    description: str | None = Field(default=None, max_length=120)


# 回复类别。前端据此决定展示哪个来源标签：
#   greeting/identity/thanks/farewell → 对话引导
#   human_service                     → 能力说明
#   knowledge                         → 知识库原文（只有这类才允许显示来源）
#   no_answer                         → 知识库未覆盖
#   fallback                          → 服务范围说明
#   unclear                           → 没听懂
ReplyType = Literal[
    "greeting",
    "identity",
    "thanks",
    "farewell",
    "human_service",
    "knowledge",
    "no_answer",
    "fallback",
    "unclear",
]


class WelcomeResponse(BaseModel):
    """首屏欢迎语。不创建会话、不写库，可重复调用。"""

    reply: str
    reply_type: ReplyType
    suggestions: list[SuggestionOut] = []


class ChatResponse(BaseModel):
    session_id: str
    session_title: str
    message_id: str
    # reply 与 answer 内容一致：reply 是对外主字段，answer 保留兼容既有前端
    reply: str
    answer: str
    reply_type: ReplyType
    suggestions: list[SuggestionOut] = []
    answer_mode: Literal["knowledge_only", "llm"]
    answer_kind: str
    intent: str
    intent_method: str
    sources: list[SourceOut] = []
    degraded: str | None = None
    retrieval: dict


# ---------------- 运行模式 ----------------
class ModeOption(BaseModel):
    value: str
    label: str
    description: str


class ModelServiceStatus(BaseModel):
    """模型服务的**可核验**状态。

    刻意没有 `available: true` 这种字段：没真正调用过就不能说可用。
    status 的四个取值分别对应：没配密钥 / 配了但没验证 / 验证过能用 / 最近一次失败。
    """

    provider: str
    model: str
    configured: bool
    status: Literal["not_configured", "unverified", "ok", "error"]
    status_text: str
    will_be_called: bool
    last_failure: dict | None = None
    last_success_at: str | None = None


class AnswerModeResponse(BaseModel):
    mode: str
    label: str
    scope: Literal["global"]
    scope_note: str
    default_mode: str
    overridden: bool
    updated_at: str | None = None
    options: list[ModeOption]
    valid_values: list[str]
    model: ModelServiceStatus


class AnswerModeUpdate(BaseModel):
    mode: str = Field(min_length=1, max_length=32)


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


class UploadPolicy(BaseModel):
    """上传限制。前端要显示"支持什么、多大"，就必须拿到后端的真实配置，
    否则界面上写死的 10MB 迟早和 MAX_UPLOAD_MB 对不上。"""

    max_mb: int
    extensions: list[str]
    accepts: str


class KnowledgeListResponse(BaseModel):
    documents: list[DocumentOut]
    index: dict
    upload: UploadPolicy


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

# ---------------- 统计 ----------------
class StatsResponse(BaseModel):
    """工作台概览。每个字段都能在数据库或索引里找到来源，
    没有埋点的指标不在此处出现（前端显示"暂无数据"）。"""

    sessions_total: int
    sessions_today: int
    messages_total: int
    messages_today: int
    assistant_total: int
    docs_total: int
    docs_indexed: int
    chunks: int
    dim: int
    index_backend: str
    answer_mix: dict[str, int]
    knowledge_ratio: float | None = None
    degraded_total: int
    feedback_helpful: int
    feedback_unhelpful: int
    answer_mode: Literal["knowledge_only", "llm"]
    mode_label: str
    generated_at: datetime
