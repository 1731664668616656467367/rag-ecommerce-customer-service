"""提示词构建。

提示词工程的核心不是“话术漂亮”，而是三条硬约束：
1. 只能依据给定资料回答（防止编造）；
2. 资料不足要承认（防止硬答）；
3. 业务数据查询没有接入就必须说明（防止假装查过订单）。
"""

from __future__ import annotations

from app.rag.retriever import RetrievalResult

SYSTEM_PROMPT = """你是某电商平台的智能客服助手。请严格遵守以下规则：

【回答依据】
1. 只能依据【知识库资料】中的内容回答业务规则类问题。
2. 如果资料中没有相关信息，必须明确说明“知识库中暂时没有相关信息”，并建议联系人工客服。
   禁止自行编造政策、时效、金额或流程。
3. 绝对不要声称你查询了订单系统、物流系统或退款系统。
   当前尚未接入这些真实业务系统，涉及个人订单状态、物流轨迹、退款进度时，
   应说明“暂时无法查询到你的订单实时状态”，并引导用户提供订单号或转人工。

【风格】
4. 使用简体中文，语气专业、简洁、礼貌，不要过度热情。
5. 先给结论，再给必要说明，控制在 200 字以内，可用短列表。
6. 不要提及“资料片段”“向量”“检索”等技术细节，直接自然地给答案。
"""

INTENT_HINT = {
    "查订单": "用户在问订单相关信息。可在规则允许范围内说明查询方式，但不得伪造具体订单状态。",
    "退款": "用户在问退款。说明退款政策与流程，不得承诺退款已成功或给出具体到账时间承诺。",
    "物流": "用户在问物流。说明配送时效规则，不得编造具体物流轨迹。",
    "售后": "用户在问售后（退换货、维修、质量问题）。说明售后规则与所需材料。",
    "其他": "用户问题不属于上述类别，按知识库资料回答，或引导转人工。",
}


def build_context_block(retrieval: RetrievalResult) -> str:
    if not retrieval.has_context:
        return "（无相关资料）"
    lines = []
    for i, h in enumerate(retrieval.hits, start=1):
        lines.append(f"[片段{i}] 来源：{h.file_name} 第{h.chunk_index + 1}段\n{h.text}")
    return "\n\n".join(lines)


def build_messages(
    question: str,
    intent: str,
    retrieval: RetrievalResult,
    history: list[dict] | None = None,
) -> list[dict]:
    """组装 OpenAI 兼容格式的消息数组。"""
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    # 只带最近几轮，控制 token 成本；不同会话的历史绝不混用
    for item in history or []:
        role = item.get("role")
        content = (item.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content[:1200]})

    user_block = (
        f"【识别意图】{intent}\n"
        f"【意图提示】{INTENT_HINT.get(intent, INTENT_HINT['其他'])}\n\n"
        f"【知识库资料】\n{build_context_block(retrieval)}\n\n"
        f"【用户问题】\n{question}"
    )
    messages.append({"role": "user", "content": user_block})
    return messages
