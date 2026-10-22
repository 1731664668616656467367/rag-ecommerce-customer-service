"""聊天业务编排。

一次提问的完整链路（knowledge_only 模式）：
    校验输入 -> 取/建会话 -> 存用户消息
    -> 对话引导规则（问候/身份/感谢/告别/人工客服）命中则短路
    -> 本地规则识别意图 -> 知识库检索（向量 + BM25 融合）-> 相关性判断
    -> 原文摘录 / 无资料（业务问题 / 超范围 / 没看懂三分支）-> 存回答

llm 模式则在检索之后多一步“调用 DeepSeek 生成”，两者共用同一套检索与会话逻辑。

关于对话引导（为什么先于检索）：
    “你好”“你是谁”“谢谢”这类发言本来就不该去知识库找答案——检索一定返回
    “最像的片段”，等于把无关政策段落硬塞给用户。所以引导类发言先由本地规则
    精确判定并短路；判定不出来的（例如“你好，我想知道退款流程”）照常进检索。
    判据见 app/customer_service/conversation_rules.py。

关于模式开关（重要）：
    是否调用大模型只看 settings.answer_mode，与“环境里有没有 API Key”无关。
    knowledge_only 模式下本模块不会构造 DeepSeek 客户端，也不会把客户端交给意图识别，
    因此不存在任何隐式外联。见 app/llm/factory.py 与 tests/test_knowledge_only.py。

关于降级：
    llm 模式下模型失败（超时/402/不可用）仍然返回 200，但 answer 只陈列知识库原文，
    并用 degraded 字段标明原因，绝不把原文包装成“模型生成的专业回复”。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session as OrmSession

from app.config import settings
from app.customer_service.conversation_rules import (
    OFF_SCOPE_TEXT,
    UNINTELLIGIBLE_TEXT,
    default_suggestions,
    has_business_topic,
    is_unintelligible,
    match_smalltalk,
    strip_request_prefix,
)
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
from app.llm.factory import get_llm_client
from app.llm import status as llm_status
from app.rag.answer import NO_KB_ANSWER, build_knowledge_answer
from app.rag.prompt import build_messages
from app.rag.retriever import get_retriever
from app.runtime_mode import effective_answer_mode
from app.services import session_service

logger = logging.getLogger(__name__)

# 兼容旧名字：无可靠资料时的固定话术
NO_CONTEXT_REPLY = NO_KB_ANSWER

BUSINESS_DATA_NOTICE = {
    "查订单": "（提示：本服务尚未接入订单系统，无法查询具体订单的实时状态。）",
    "物流": "（提示：本服务尚未接入物流系统，无法查询实时物流轨迹。）",
    "退款": "（提示：本服务尚未接入退款系统，无法确认退款进度或到账时间。）",
}


class ChatInputError(Exception):
    pass


_MD_HEADING = re.compile(r"#{1,6}\s*")


def _plain_snippet(text: str, limit: int = 180) -> str:
    """把 Markdown 片段压成一段可读的纯文本，去掉 #、多余空行。"""
    cleaned = _MD_HEADING.sub("", text)
    cleaned = re.sub(r"\s*\n\s*", " ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned[:limit] + "…" if len(cleaned) > limit else cleaned


def _extractive_answer(retrieval, intent: str, reason: str) -> str:
    """llm 模式下模型不可用时的降级回答：只陈列检索原文，不新增任何结论。"""
    if not retrieval.has_context:
        return NO_CONTEXT_REPLY
    lines = [f"当前未能调用大模型（原因：{reason}）。以下为知识库中检索到的原文，供你参考："]
    for i, h in enumerate(retrieval.hits[:2], start=1):
        lines.append(f"{i}. {_plain_snippet(h.text)}\n   —— {h.file_name} 第 {h.chunk_index + 1} 段")
    lines.append("如需更准确的答复，请联系人工客服。")
    return "\n".join(lines)


def _with_business_notice(answer: str, intent: str) -> str:
    notice = BUSINESS_DATA_NOTICE.get(intent)
    if notice and notice not in answer:
        return f"{answer}\n\n{notice}"
    return answer


def _resolve_client(llm: LLMClient | None) -> LLMClient | None:
    """唯一的客户端入口。

    knowledge_only 时返回 None —— 即使调用方硬塞了一个客户端，也不会被使用。
    这是“纯知识库模式不调用外部模型”的代码级保证，而不是靠约定。

    判断走 effective_answer_mode()：用户在主页面切换模式后立即生效，
    不需要重启进程，也不依赖前端传什么参数进来。
    """
    if effective_answer_mode() != "llm":
        return None
    if llm is not None:
        return llm
    return get_llm_client()


def _skipped_retrieval() -> dict:
    """引导类发言没有走检索，这里给出结构一致的空检索结果。

    不下发 embedding 字段的具体值：取它需要构造 embedder，
    而 embedder 构造时会探测 Ollama。问候语不该为了一次探测多等几秒。
    """
    return {
        "has_context": False,
        "top_score": 0.0,
        "reason": "skipped_smalltalk",
        "embedding": "",
        "methods": [],
        "threshold": 0.0,
    }


@dataclass
class BusinessAnswer:
    """业务链路的产出。用命名结构而不是长元组，避免位置写错还悄悄跑通。"""

    answer: str
    answer_kind: str
    reply_type: str
    suggestions: list[dict]
    intent: str
    intent_method: str
    degraded: str | None
    sources: list[dict]
    retrieval_payload: dict


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

    mode = effective_answer_mode()

    # 1) 会话
    if session_id:
        session = session_service.get_session(db, session_id)  # 不存在 -> SessionNotFound
    else:
        session = session_service.create_session(db)
    session_service.touch_title_if_default(db, session, text)

    # 2) 先落库用户消息，保证即使后面失败也不丢用户输入
    session_service.add_message(db, session.id, "user", text)

    # 3) 对话引导：纯本地规则，命中就短路，不检索、不调模型
    smalltalk = match_smalltalk(text)
    if smalltalk is not None:
        answer = smalltalk.text
        reply_type = smalltalk.kind
        answer_kind = "conversation"
        suggestions = smalltalk.suggestions
        intent = "其他"
        intent_method = "rule"
        degraded = None
        sources: list[dict] = []
        retrieval_payload = _skipped_retrieval()
    else:
        biz = await _answer_business(db, session, text, mode, llm)
        answer = biz.answer
        answer_kind = biz.answer_kind
        reply_type = biz.reply_type
        suggestions = biz.suggestions
        intent = biz.intent
        intent_method = biz.intent_method
        degraded = biz.degraded
        sources = biz.sources
        retrieval_payload = biz.retrieval_payload

    answer = _with_business_notice(answer, intent)

    # 6) 存回答（来源信息一起存，刷新页面后仍能看到依据）
    assistant_msg: Message = session_service.add_message(
        db,
        session.id,
        "assistant",
        answer,
        intent=intent,
        sources=sources,
        degraded=degraded,
        answer_mode=mode,
        reply_type=reply_type,
    )

    return {
        "session_id": session.id,
        "session_title": session.title,
        "message_id": assistant_msg.id,
        "answer": answer,
        # reply 与 answer 内容相同：reply 是对外的新字段名，answer 保留兼容旧前端
        "reply": answer,
        "reply_type": reply_type,
        "suggestions": suggestions,
        "answer_mode": mode,
        "answer_kind": answer_kind,
        "intent": intent,
        "intent_method": intent_method,
        "sources": sources,
        "degraded": degraded,
        "retrieval": retrieval_payload,
    }


async def _answer_business(
    db: OrmSession,
    session,
    text: str,
    mode: str,
    llm: LLMClient | None,
) -> BusinessAnswer:
    """走完“意图识别 -> 检索 -> 生成”的业务链路。"""
    # 意图识别：knowledge_only 模式下不会传 llm，纯本地规则
    client = _resolve_client(llm)
    # 去客套前缀后再做意图识别与检索：“你好，我想退款” → “退款”
    query = strip_request_prefix(text)
    intent_result = await classify_intent(query, client)
    intent = validate_intent(intent_result["intent"])

    retrieval = get_retriever().retrieve(query)

    degraded: str | None = None
    answer_kind: str
    answer: str

    if mode == "knowledge_only":
        ka = build_knowledge_answer(retrieval, intent)
        answer = ka.text
        answer_kind = ka.kind
    else:
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
            if client is None:
                raise LLMNotConfigured()
            answer = await client.complete(messages, temperature=0.3)
            answer_kind = "llm"
            llm_status.record_success()
        except LLMNotConfigured:
            degraded = "llm_not_configured"
            llm_status.record_failure(degraded)
            answer = _extractive_answer(retrieval, intent, "未配置 DEEPSEEK_API_KEY 或未启用")
            answer_kind = "llm_degraded"
        except LLMTimeout:
            degraded = "llm_timeout"
            llm_status.record_failure(degraded)
            answer = _extractive_answer(retrieval, intent, "大模型响应超时")
            answer_kind = "llm_degraded"
        except LLMQuotaExceeded:
            degraded = "llm_quota_exceeded"
            llm_status.record_failure(degraded)
            answer = _extractive_answer(retrieval, intent, "大模型账户余额不足")
            answer_kind = "llm_degraded"
        except LLMUnavailable as exc:
            degraded = "llm_unavailable"
            llm_status.record_failure(degraded, str(exc))
            logger.warning("模型不可用：%s", exc.code)
            answer = _extractive_answer(retrieval, intent, "大模型服务暂时不可用")
            answer_kind = "llm_degraded"
        except LLMError as exc:
            degraded = exc.code
            llm_status.record_failure(degraded, str(exc))
            answer = _extractive_answer(retrieval, intent, "模型调用失败")
            answer_kind = "llm_degraded"

    if not answer.strip():
        answer = NO_CONTEXT_REPLY
        answer_kind = "no_answer"

    # 4) 没找到可靠资料时再细分三种情况，而不是一句“没找到”打发所有人
    #    条件写成 “没有检索依据，且这次没有拿到模型回答”：
    #    llm 模式下模型失败降级（llm_degraded）时同样没有依据，
    #    以前会被归成 knowledge，前端就会贴出“知识库原文”却一条来源都没有。
    reply_type: str
    suggestions: list[dict]
    if not retrieval.has_context and answer_kind != "llm":
        if intent == "其他":
            if is_unintelligible(text):
                # 看不懂：请用户换个说法
                answer, reply_type = UNINTELLIGIBLE_TEXT, "unclear"
                answer_kind = "conversation"
            elif has_business_topic(text):
                # 有业务词但意图规则没归到四类里（例如“运费为什么这么贵”）。
                # 这仍然是我们范围内的问题，只能诚实说知识库没找到，
                # 不能说成“与电商无关”，那等于把用户推走。
                reply_type = "no_answer"
            else:
                # 与电商无关：说明服务范围
                answer, reply_type = OFF_SCOPE_TEXT, "fallback"
                answer_kind = "conversation"
        else:
            # 是业务问题，但知识库确实没有依据 —— 保持原本的诚实话术
            reply_type = "no_answer"
        suggestions = default_suggestions()
    else:
        reply_type = "knowledge"
        suggestions = []

    retrieval_payload = {
        "has_context": retrieval.has_context,
        "top_score": round(retrieval.top_score, 4),
        "reason": retrieval.reason,
        "embedding": retrieval.used_provider,
        "methods": retrieval.methods,
        "threshold": retrieval.threshold,
    }
    return BusinessAnswer(
        answer=answer,
        answer_kind=answer_kind,
        reply_type=reply_type,
        suggestions=suggestions,
        intent=intent,
        intent_method=intent_result["method"],
        degraded=degraded,
        sources=retrieval.sources(),
        retrieval_payload=retrieval_payload,
    )


def welcome_payload() -> dict:
    """首屏欢迎语 + 快捷问题。不建会话、不写库，可安全重复调用。"""
    from app.customer_service.conversation_rules import GREETING_TEXT

    return {
        "reply": GREETING_TEXT,
        "reply_type": "greeting",
        "suggestions": default_suggestions(),
    }
