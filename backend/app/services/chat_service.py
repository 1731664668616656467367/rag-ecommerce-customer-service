"""聊天业务编排。

一次提问的完整链路：
    校验输入 -> 取/建会话 -> 存用户消息 -> 识别意图 -> 检索知识库
    -> 组装提示词（含最近历史）-> 调 DeepSeek -> 校验结果 -> 存回答 -> 返回

关于“模型不可用”的处理策略（有意为之）：
    客服场景下，直接给用户一个 5xx 白屏体验很差，所以我们返回 200，
    但回答里明确标注 degraded 原因，并且只展示“检索到的原文”，
    绝不假装那是大模型生成的专业回复。前端会把降级状态显示成黄色提示。
"""

from __future__ import annotations

import logging
import re

from sqlalchemy.orm import Session as OrmSession

from app.config import settings
from app.customer_service.intent import classify_intent, validate_intent
from app.db.models import Message
from app.llm.base import (
    LLMClient,
    LLMError,
    LLMNotConfigured,
    LLMQuotaExceeded,
    LLMTimeout,
    LLMUnavailable,
)
from app.llm.deepseek_client import DeepSeekClient
from app.rag.prompt import build_messages
from app.rag.retriever import get_retriever
from app.services import session_service

logger = logging.getLogger(__name__)

NO_CONTEXT_REPLY = (
    "抱歉，知识库中暂时没有与该问题相关的信息，我无法给出准确答复。"
    "建议你补充订单号等细节，或点击「转人工」由客服同事为你处理。"
)

BUSINESS_DATA_NOTICE = {
    "查订单": "（提示：本服务尚未接入订单系统，无法查询具体订单的实时状态。）",
    "物流": "（提示：本服务尚未接入物流系统，无法查询实时物流轨迹。）",
    "退款": "（提示：本服务尚未接入退款系统，无法确认退款进度或到账时间。）",
}


class ChatInputError(Exception):
    pass


def _llm_or_none() -> DeepSeekClient:
    return DeepSeekClient()


_MD_HEADING = re.compile(r"#{1,6}\s*")


def _plain_snippet(text: str, limit: int = 180) -> str:
    """把 Markdown 片段压成一段可读的纯文本，去掉 #、多余空行。"""
    cleaned = _MD_HEADING.sub("", text)
    cleaned = re.sub(r"\s*\n\s*", " ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned[:limit] + "…" if len(cleaned) > limit else cleaned


def _extractive_answer(retrieval, intent: str, reason: str) -> str:
    """没有大模型时的降级回答：只陈列检索原文，不新增任何结论。"""
    if not retrieval.has_context:
        return NO_CONTEXT_REPLY
    lines = [f"当前未启用智能生成（原因：{reason}）。以下为知识库中检索到的原文，供你参考："]
    for i, h in enumerate(retrieval.hits[:2], start=1):
        lines.append(f"{i}. {_plain_snippet(h.text)}\n   —— {h.file_name} 第 {h.chunk_index + 1} 段")
    lines.append("如需更准确的答复，请联系人工客服。")
    return "\n".join(lines)


def _with_business_notice(answer: str, intent: str) -> str:
    notice = BUSINESS_DATA_NOTICE.get(intent)
    if notice and notice not in answer:
        return f"{answer}\n\n{notice}"
    return answer


async def handle_chat(
    db: OrmSession,
    message: str,
    session_id: str | None = None,
    llm: LLMClient | None = None,
) -> dict:
    text = (message or "").strip()
    if not text:
        raise ChatInputError("消息不能为空")
    if len(text) > settings.max_message_chars:
        raise ChatInputError(f"消息过长，最多 {settings.max_message_chars} 字")

    # 1) 会话
    if session_id:
        session = session_service.get_session(db, session_id)  # 不存在 -> SessionNotFound
    else:
        session = session_service.create_session(db)
    session_service.touch_title_if_default(db, session, text)

    # 2) 先落库用户消息，保证即使后面失败也不丢用户输入
    session_service.add_message(db, session.id, "user", text)

    # 3) 意图识别（规则优先，模型兜底，最终白名单校验）
    client = llm if llm is not None else _llm_or_none()
    intent_result = await classify_intent(text, client if getattr(client, "configured", True) else None)
    intent = validate_intent(intent_result["intent"])

    # 4) 检索
    retrieval = get_retriever().retrieve(text)

    # 5) 生成
    degraded: str | None = None
    answer: str
    if retrieval.has_context:
        messages = build_messages(
            text,
            intent,
            retrieval,
            history=session_service.recent_history(db, session.id)[:-1],
        )
    else:
        messages = build_messages(text, intent, retrieval, history=[])

    try:
        if not getattr(client, "configured", True):
            raise LLMNotConfigured()
        answer = await client.complete(messages, temperature=0.3)
    except LLMNotConfigured:
        degraded = "llm_not_configured"
        answer = _extractive_answer(retrieval, intent, "后端未配置 DEEPSEEK_API_KEY")
    except LLMTimeout:
        degraded = "llm_timeout"
        answer = _extractive_answer(retrieval, intent, "大模型响应超时")
    except LLMQuotaExceeded:
        degraded = "llm_quota_exceeded"
        answer = _extractive_answer(retrieval, intent, "大模型账户余额不足")
    except LLMUnavailable as exc:
        degraded = "llm_unavailable"
        logger.warning("模型不可用：%s", exc.code)
        answer = _extractive_answer(retrieval, intent, "大模型服务暂时不可用")
    except LLMError as exc:
        degraded = exc.code
        answer = _extractive_answer(retrieval, intent, "模型调用失败")

    if not answer.strip():
        answer = NO_CONTEXT_REPLY
    answer = _with_business_notice(answer, intent)

    # 6) 存回答（来源信息一起存，刷新页面后仍能看到依据）
    sources = retrieval.sources()
    assistant_msg: Message = session_service.add_message(
        db, session.id, "assistant", answer, intent=intent, sources=sources, degraded=degraded
    )

    return {
        "session_id": session.id,
        "session_title": session.title,
        "message_id": assistant_msg.id,
        "answer": answer,
        "intent": intent,
        "intent_method": intent_result["method"],
        "sources": sources,
        "degraded": degraded,
        "retrieval": {
            "has_context": retrieval.has_context,
            "top_score": round(retrieval.top_score, 4),
            "reason": retrieval.reason,
            "embedding": retrieval.used_provider,
        },
    }
