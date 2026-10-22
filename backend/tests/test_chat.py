"""聊天链路测试：正常问答、空输入、模型失败、会话不存在。"""

from __future__ import annotations

import pytest

from app.services import chat_service, session_service
from tests.support import FakeLLM, QuotaLLM, TimeoutLLM, UnavailableLLM


def test_chat_in_knowledge_mode_returns_excerpt(client, indexed_doc):
    """默认纯知识库模式：不降级、不调用模型，直接返回原文摘录与来源。"""
    resp = client.post("/api/chat", json={"message": "退款一般几天到账？"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["answer_mode"] == "knowledge_only"
    assert data["answer_kind"] == "knowledge_extract"
    assert data["degraded"] is None
    assert data["sources"], "检索到的来源必须返回"
    assert "原文摘录" in data["answer"]
    assert "1 至 3 个工作日" in data["answer"]
    assert data["intent"] == "退款"
    assert data["session_id"]


def test_chat_with_fake_llm_uses_retrieved_context(client, indexed_doc, monkeypatch, llm_mode):
    fake = FakeLLM(reply="质量问题可在签收后15日内申请退货，需提供故障照片。")
    monkeypatch.setattr(chat_service, "get_llm_client", lambda: fake)

    resp = client.post("/api/chat", json={"message": "收到的商品有质量问题，可以退货吗"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["degraded"] is None
    assert data["answer_mode"] == "llm"
    assert data["answer_kind"] == "llm"
    assert data["answer"] == fake.reply
    assert data["sources"][0]["file_name"] == "退换货政策.md"

    prompt = fake.calls[-1][-1]["content"]
    assert "【知识库资料】" in prompt
    assert "退换货政策.md" in prompt
    assert "质量问题" in prompt


def test_chat_without_context_and_fake_llm(client, monkeypatch, llm_mode):
    """知识库为空时，提示词里也要明确写“无相关资料”，而不是留空让模型自由发挥。"""
    fake = FakeLLM(reply="知识库中暂时没有相关信息，建议联系人工客服。")
    monkeypatch.setattr(chat_service, "get_llm_client", lambda: fake)

    resp = client.post("/api/chat", json={"message": "火星探测器什么时候发射"})
    data = resp.json()
    assert data["retrieval"]["has_context"] is False
    assert "（无相关资料）" in fake.calls[-1][-1]["content"]


@pytest.mark.parametrize("payload", [{}, {"message": ""}, {"message": "   "}])
def test_chat_rejects_empty_message(client, payload):
    resp = client.post("/api/chat", json=payload)
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


def test_chat_rejects_too_long_message(client):
    resp = client.post("/api/chat", json={"message": "退" * 5000})
    assert resp.status_code == 422


def test_chat_with_unknown_session_returns_404(client):
    resp = client.post("/api/chat", json={"message": "退款", "session_id": "deadbeef"})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "会话不存在"


async def test_service_handles_timeout(llm_mode, db, indexed_doc):
    result = await chat_service.handle_chat(
        db, "退款几天到账", llm=TimeoutLLM()
    )
    assert result["degraded"] == "llm_timeout"
    assert result["sources"]
    assert "超时" in result["answer"]


async def test_service_handles_unavailable(llm_mode, db, indexed_doc):
    result = await chat_service.handle_chat(db, "退款几天到账", llm=UnavailableLLM())
    assert result["degraded"] == "llm_unavailable"
    assert result["answer"]


async def test_service_handles_quota_exceeded(llm_mode, db, indexed_doc):
    """402 余额不足必须单独标记，不能笼统说“服务不可用”。"""
    result = await chat_service.handle_chat(db, "退款几天到账", llm=QuotaLLM())
    assert result["degraded"] == "llm_quota_exceeded"
    assert "余额不足" in result["answer"]
    assert result["sources"]


async def test_service_notice_for_order_intent(llm_mode, db):
    result = await chat_service.handle_chat(db, "帮我查一下我的订单到哪了", llm=FakeLLM())
    assert result["intent"] == "查订单"
    # 未接入订单系统时必须如实告知，不能编造订单状态
    assert "尚未接入订单系统" in result["answer"]


async def test_user_message_saved_even_if_llm_fails(llm_mode, db, indexed_doc):
    with pytest.raises(chat_service.ChatInputError):
        await chat_service.handle_chat(db, "   ", llm=FakeLLM())

    result = await chat_service.handle_chat(db, "退款几天到账", llm=TimeoutLLM())
    msgs = session_service.list_messages(db, result["session_id"])
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[0].content == "退款几天到账"


async def test_empty_message_raises_input_error(llm_mode, db):
    with pytest.raises(chat_service.ChatInputError):
        await chat_service.handle_chat(db, "", llm=FakeLLM())
