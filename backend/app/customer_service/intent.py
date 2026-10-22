"""电商客服意图识别。

工程上最容易犯的错：把大模型输出的自由文本直接当成业务标签。
模型可能回 "查订单。" / "订单查询" / "查询订单意图" / "I think it's 退款"，
这些都不是合法枚举值。所以流程是：

    1. 关键词规则先判断（快、稳、零成本，覆盖大部分常见问法）；
    2. 规则不确定时再问大模型，要求输出严格 JSON；
    3. 无论来源如何，最后都必须经过 validate_intent 的白名单校验；
    4. 校验不过就退回 "其他"，并记录原因，绝不把脏数据写进数据库。
"""

from __future__ import annotations

import json
import logging
import re

from app.config import settings
from app.llm.base import LLMClient, LLMError

logger = logging.getLogger(__name__)

INTENTS: tuple[str, ...] = ("查订单", "退款", "物流", "售后", "其他")
DEFAULT_INTENT = "其他"

# 关键词表：每个词带权重。为什么不用“命中个数”？
#   “签收”在物流里出现，“质量问题”在售后里出现，两者都命中 1 次就会打成平手，
#   而“质量问题”明显更能代表意图。所以强特征给高权重，弱特征给低权重。
#   实测：'商品有质量问题，签收后多久内可以退货？' 曾被错分到物流，加权重后归为售后。
RULES: dict[str, tuple[tuple[str, float], ...]] = {
    "退款": (
        ("退货退款", 3.0),
        ("退款", 2.0),
        ("退钱", 2.0),
        ("申请退", 2.0),
        ("钱退", 2.0),
        ("退回来", 2.0),
        ("退我", 2.0),
        ("原路退回", 2.0),
        ("退单", 2.0),
        ("退费", 2.0),
        ("退款进度", 2.5),
    ),
    "物流": (
        ("物流", 2.0),
        ("快递", 2.0),
        ("运单", 2.0),
        ("单号", 2.0),
        ("发货", 2.0),
        ("配送", 2.0),
        ("派送", 2.0),
        ("几天能到", 2.0),
        ("什么时候到", 2.0),
        ("还没收到", 1.5),
        ("运输", 1.5),
        ("到哪", 1.5),
        ("到货", 1.5),
        ("顺丰", 1.5),
        ("签收", 1.0),
    ),
    "售后": (
        ("售后服务", 3.0),
        # “售后”这个词本身以前漏了：用户问“如何申请售后服务”，
        # 规则一个词都不中，被归成“其他”，再叠加知识库没命中就变成了
        # “我不提供这个服务”——明明在服务范围内，却把用户推走。
        ("售后", 2.5),
        ("质量问题", 3.0),
        ("换货", 2.5),
        ("维修", 2.5),
        ("保修", 2.5),
        ("三包", 2.5),
        ("退货", 2.5),
        ("坏了", 2.0),
        ("破损", 2.0),
        ("少件", 2.0),
        ("漏发", 2.0),
        ("错发", 2.0),
        ("退换", 2.0),
        ("有瑕疵", 2.0),
        ("七天无理由", 2.5),
        ("不想要了", 1.5),
    ),
    "查订单": (
        ("收货地址", 2.5),
        ("订单状态", 2.5),
        ("订单号", 2.5),
        ("订单", 2.0),
        ("我的单", 2.0),
        ("购买记录", 2.0),
        ("查单", 2.0),
        ("待发货", 2.0),
        ("待收货", 2.0),
        ("下单", 1.5),
        ("买的", 1.5),
        ("地址", 1.5),
    ),
}

_VALID = set(INTENTS)
_CODE_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def rule_classify(question: str) -> tuple[str, float]:
    """返回 (意图, 得分)。得分为 0 时表示规则无法判断。"""
    q = question.lower()
    best, best_score = DEFAULT_INTENT, 0.0
    for intent, words in RULES.items():
        score = sum(weight for kw, weight in words if kw in q)
        if score > best_score:
            best, best_score = intent, score
    return best, best_score


def parse_intent_candidate(raw: str) -> str | None:
    """从模型输出里尽力提取“原始候选标签”。只做提取，不做兜底。

    返回 None 表示完全没提取到可用的意图词；
    返回的字符串也可能不合法（比如 "退货"），由调用方决定接受还是拒绝。
    """
    if not raw:
        return None
    text = raw.strip()

    # 优先解析 JSON
    m = _CODE_FENCE.search(text)
    text_json = m.group(1).strip() if m else text
    try:
        obj = json.loads(text_json)
        if isinstance(obj, dict):
            for key in ("intent", "label", "category", "意图"):
                if key in obj and isinstance(obj[key], str):
                    return obj[key].strip()
    except json.JSONDecodeError:
        pass

    # 退化为“包含匹配”，注意顺序：先长后短，避免 "退款" 抢走 "退货退款"
    for intent in sorted(INTENTS, key=len, reverse=True):
        if intent in text:
            return intent
    return None


def extract_intent_token(raw: str) -> str:
    """提取 + 白名单归一化。无法识别时返回“其他”。"""
    candidate = parse_intent_candidate(raw)
    return validate_intent(candidate)


def validate_intent(raw: str | None) -> str:
    """白名单校验。任何不在 INTENTS 里的值都归为“其他”。"""
    if not raw:
        return DEFAULT_INTENT
    value = str(raw).strip().strip("，。.!！\"'` ")
    return value if value in _VALID else DEFAULT_INTENT


INTENT_PROMPT = """你是电商客服意图分类器。把用户问题归类为以下之一：
查订单 / 退款 / 物流 / 售后 / 其他

只输出 JSON，格式：{{"intent":"退款"}}
不要输出解释、标点以外的任何内容。

用户问题：{question}"""


async def classify_intent(question: str, llm: LLMClient | None = None) -> dict:
    """返回 {"intent": str, "method": "rule"|"llm"|"fallback", "valid": bool}

    knowledge_only 模式下即使调用方传入 llm 也会被忽略：
    意图识别必须完全由本地规则完成，这是纯知识库模式的定义之一。
    """
    if llm is not None and not settings.llm_enabled:
        logger.info("knowledge_only 模式：忽略传入的模型客户端，仅使用本地规则")
        llm = None

    question = (question or "").strip()
    if not question:
        return {"intent": DEFAULT_INTENT, "method": "fallback", "valid": True}

    rule_intent, hits = rule_classify(question)
    if hits >= 2:
        # 两条以上关键词命中，规则结果已经足够可靠，省掉一次模型调用
        return {"intent": rule_intent, "method": "rule", "valid": True}

    if llm is not None:
        try:
            raw = await llm.complete(
                [{"role": "user", "content": INTENT_PROMPT.format(question=question)}],
                temperature=0.0,
            )
            candidate = parse_intent_candidate(raw)
            # 关键：先判断“候选值是否在白名单里”，再做归一化。
            # 否则非法值会被 validate_intent 悄悄改成“其他”，看起来像识别成功。
            if candidate is not None and candidate in _VALID:
                return {"intent": candidate, "method": "llm", "valid": True}
            logger.warning("模型返回非法意图（已拒绝）：%r", (candidate or "")[:40])
            # 不直接返回：继续走下面的规则兜底，规则命中一条也算有效信息
            llm_invalid = True
        except LLMError as exc:
            llm_invalid = False
            logger.warning("意图识别模型不可用（%s），改用规则结果", exc.code)
    else:
        llm_invalid = False

    if hits == 1:
        return {
            "intent": rule_intent,
            "method": "rule",
            "valid": True,
        }
    if llm_invalid:
        return {"intent": DEFAULT_INTENT, "method": "llm_invalid", "valid": False}
    return {"intent": DEFAULT_INTENT, "method": "fallback", "valid": True}
