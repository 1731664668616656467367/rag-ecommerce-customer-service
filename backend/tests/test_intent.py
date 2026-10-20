"""意图识别单元测试：合法性与非法输出的校验。"""

from __future__ import annotations

import pytest

from app.customer_service.intent import (
    INTENTS,
    classify_intent,
    extract_intent_token,
    rule_classify,
    validate_intent,
)
from tests.support import FakeLLM


@pytest.mark.parametrize(
    "question,expected",
    [
        ("我要退款，钱什么时候退回来", "退款"),
        ("我的快递到哪了，什么时候能到", "物流"),
        ("收到的手机屏幕坏了，能换货吗", "售后"),
        ("帮我查一下订单状态", "查订单"),
        ("你们公司在哪里", "其他"),
    ],
)
def test_rule_classify(question, expected):
    intent, hits = rule_classify(question)
    assert intent == expected
    # “其他”本来就该是零命中；其它类别至少要命中一个关键词
    assert hits >= 1 if expected != "其他" else hits == 0


@pytest.mark.parametrize(
    "raw", ["退款", "退款。", " 退款 ", '"退款"', "`退款`"]
)
def test_validate_intent_accepts_legal_values(raw):
    assert validate_intent(raw) == "退款"


@pytest.mark.parametrize(
    "raw", ["退货", "refund", "查订单意图", "", None, "'; DROP TABLE users;--"]
)
def test_validate_intent_rejects_illegal_values(raw):
    assert validate_intent(raw) == "其他"
    assert validate_intent(raw) in INTENTS


def test_extract_intent_token_from_json():
    assert extract_intent_token('{"intent":"物流"}') == "物流"
    assert extract_intent_token('```json\n{"intent":"售后"}\n```') == "售后"


def test_extract_intent_token_from_prose():
    assert extract_intent_token("我认为这个问题属于退款类") == "退款"


def test_extract_intent_token_garbage_falls_back():
    assert extract_intent_token("我不知道该怎么分类") == "其他"


async def test_llm_based_classification():
    llm = FakeLLM(intent_reply='{"intent":"售后"}')
    result = await classify_intent("东西有点问题", llm)
    assert result["intent"] == "售后"
    assert result["method"] == "llm"


async def test_llm_invalid_output_is_rejected():
    llm = FakeLLM(intent_reply='{"intent":"投诉建议"}')
    result = await classify_intent("东西有点问题", llm)
    assert result["intent"] == "其他"
    assert result["valid"] is False
    assert result["method"] == "llm_invalid"


async def test_rule_shortcut_skips_llm():
    """命中两个以上关键词时不应该浪费一次模型调用。"""
    llm = FakeLLM(intent_reply='{"intent":"其他"}')
    result = await classify_intent("我要退款，钱退回来要多久", llm)
    assert result["method"] == "rule"
    assert llm.calls == []


async def test_llm_error_falls_back_to_rules():
    from tests.support import UnavailableLLM

    result = await classify_intent("东西有点问题", UnavailableLLM())
    assert result["intent"] in INTENTS
    assert result["method"] in ("rule", "fallback")
