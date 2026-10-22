"""对话引导（欢迎语 / 闲聊）与快捷问题测试。

这组测试要守住的核心不是“话术对不对”，而是**边界**：
    1. 纯问候要被识别，并且不进入检索（否则问候语会捞回一段无关政策原文）；
    2. 带问候的业务问题不能被抢走（“你好，我想退款”必须仍然查到退款政策）；
    3. 引导类回复不能冒充“知识库原文”，也不能编造电话/链接/订单状态；
    4. 每个快捷问题都必须真的能走到一条真实链路，不能点完只是换句话术。

第 9 项（零外联）与 tests/test_knowledge_only.py 共用 conftest 里的 no_network 拦截器。
"""

from __future__ import annotations

import re

import pytest

from app.config import settings
from app.customer_service.conversation_rules import (
    DEFAULT_SUGGESTIONS,
    FAREWELL_TEXT,
    GREETING_TEXT,
    HUMAN_SERVICE_TEXT,
    IDENTITY_TEXT,
    OFF_SCOPE_TEXT,
    THANKS_TEXT,
    UNINTELLIGIBLE_TEXT,
    default_suggestions,
    is_unintelligible,
    match_smalltalk,
    strip_request_prefix,
)

# 全部合法的 reply_type。任何一条回复都必须落在这个集合里，
# 前端才能据此决定显示哪种来源标签。
VALID_REPLY_TYPES = {
    "greeting",
    "identity",
    "thanks",
    "farewell",
    "human_service",
    "knowledge",
    "no_answer",
    "fallback",
    "unclear",
}

# 这些回复意味着“系统没听懂/不打算答”，快捷问题绝不能被归到这类
OFF_TOPIC = {"fallback", "unclear"}


def ask(client, message: str, session_id: str | None = None) -> dict:
    payload: dict = {"message": message}
    if session_id:
        payload["session_id"] = session_id
    resp = client.post("/api/chat", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["reply_type"] in VALID_REPLY_TYPES
    # reply 与 answer 必须一致，否则前端读一个字段、旧调用方读另一个，会看到两种答案
    assert data["reply"] == data["answer"]
    return data


# ---------- 1. 纯问候 → 欢迎语 ----------


@pytest.mark.parametrize("message", ["你好", "您好", "在吗", "在不在", "有人吗", "hello", "早上好"])
def test_greeting_returns_welcome(client, indexed_doc, message):
    data = ask(client, message)

    assert data["reply_type"] == "greeting"
    assert data["reply"] == GREETING_TEXT
    assert data["answer_kind"] == "conversation"
    # 引导类发言不检索：既不该有来源，检索原因也要能解释清楚
    assert data["sources"] == []
    assert data["retrieval"]["reason"] == "skipped_smalltalk"
    assert data["retrieval"]["has_context"] is False
    # 没有知识库命中，就不能给“知识库未覆盖”这种标签
    assert data["intent"] == "其他"
    assert data["intent_method"] == "rule"
    assert len(data["suggestions"]) == 6
    assert data["degraded"] is None


# ---------- 2. 带问候的业务问题 → 仍然进检索（本轮最关键的一条） ----------


@pytest.mark.parametrize(
    "message",
    [
        "你好，我想退款",
        "你好，我想知道退款流程",
        "您好，退款一般几天到账",
        "在吗，我要退货",
        "你好，我要换货",
    ],
)
def test_greeting_with_business_topic_still_retrieves(client, indexed_doc, message):
    data = ask(client, message)

    assert data["reply_type"] == "knowledge", f"{message} 被误判成闲聊了"
    assert data["sources"], "业务问题必须带来源"
    assert data["answer_kind"] == "knowledge_extract"
    assert data["retrieval"]["reason"] != "skipped_smalltalk"
    assert data["suggestions"] == [], "业务答案不挂快捷问题，避免干扰阅读"


def test_greeting_with_business_topic_is_not_smalltalk_at_rule_level():
    """规则层单测：不依赖知识库，直接证明“含问候词”不等于“是问候”。"""
    for message in ["你好，我想退款", "您好，请问物流几天能到", "你好 我要开发票", "在吗，退款到哪一步了"]:
        assert match_smalltalk(message) is None, message


def test_pure_greeting_is_smalltalk_at_rule_level():
    match = match_smalltalk("你好")
    assert match is not None
    assert match.kind == "greeting"
    assert match.text == GREETING_TEXT


# ---------- 3. 身份介绍 ----------


@pytest.mark.parametrize("message", ["你是谁", "你是什么", "你能做什么", "你能帮我做什么"])
def test_identity_question(client, indexed_doc, message):
    data = ask(client, message)
    assert data["reply_type"] == "identity"
    assert data["reply"] == IDENTITY_TEXT
    assert data["sources"] == []
    assert len(data["suggestions"]) == 6


# ---------- 4. 感谢 ----------


@pytest.mark.parametrize("message", ["谢谢", "谢谢你", "感谢", "多谢", "thanks"])
def test_thanks_reply_keeps_conversation_open(client, indexed_doc, message):
    data = ask(client, message)
    assert data["reply_type"] == "thanks"
    assert data["reply"] == THANKS_TEXT
    # 回应致谢后要允许继续提问，所以附带快捷问题
    assert len(data["suggestions"]) == 6
    assert data["sources"] == []


# ---------- 5. 告别 ----------


@pytest.mark.parametrize("message", ["再见", "拜拜", "byebye"])
def test_farewell(client, indexed_doc, message):
    data = ask(client, message)
    assert data["reply_type"] == "farewell"
    assert data["reply"] == FAREWELL_TEXT


# ---------- 6. 无关问题 → 服务范围说明 + 快捷问题 ----------


@pytest.mark.parametrize(
    "message",
    ["今天天气怎么样", "帮我写一首诗", "推荐一部电影", "1+1等于几", "天王盖地虎"],
)
def test_off_scope_question_explains_service_scope(client, indexed_doc, message):
    data = ask(client, message)
    assert data["reply_type"] == "fallback"
    assert data["reply"] == OFF_SCOPE_TEXT
    assert data["sources"] == []
    assert len(data["suggestions"]) == 6
    # 服务范围说明不能被贴成“知识库未覆盖”，那样会让用户以为系统里有这方面资料只是没找到
    assert data["answer_kind"] == "conversation"


# ---------- 7. 看不懂 → 请重述 ----------


@pytest.mark.parametrize("message", ["？？？", "。。。", "777", "aaaa"])
def test_unintelligible_asks_for_rephrase(client, indexed_doc, message):
    data = ask(client, message)
    assert data["reply_type"] == "unclear"
    assert data["reply"] == UNINTELLIGIBLE_TEXT
    assert len(data["suggestions"]) == 6


def test_unintelligible_does_not_swallow_short_business_words():
    """单个字/短词不能一律当成“看不懂”，否则“退款”两个字也会被拦掉。"""
    assert is_unintelligible("？？？") is True
    assert is_unintelligible("谢谢") is False
    assert is_unintelligible("退款") is False


# ---------- 8. 业务问题仍走知识库，且带来源 ----------


@pytest.mark.parametrize(
    "message",
    ["退款一般几天到账？", "收到的商品有质量问题，可以退货吗", "换货需要多长时间"],
)
def test_business_question_returns_knowledge_with_sources(client, indexed_doc, message):
    data = ask(client, message)
    assert data["reply_type"] == "knowledge"
    assert data["sources"]
    assert data["sources"][0]["file_name"] == "退换货政策.md"
    assert "原文摘录" in data["reply"]
    assert data["retrieval"]["has_context"] is True
    assert data["degraded"] is None


# ---------- 9. 人工客服：只能说明能力，不能编联系方式 ----------


@pytest.mark.parametrize("message", ["我想联系人工客服", "转人工", "人工客服"])
def test_human_service_states_limitation_without_fabricating_contacts(client, indexed_doc, message):
    data = ask(client, message)
    assert data["reply_type"] == "human_service"
    assert data["reply"] == HUMAN_SERVICE_TEXT
    # 没有人工客服系统，就不能声称已转接，也不能编电话/链接/工单号
    assert not re.search(r"1[3-9]\d{9}|400[-\s]?\d{3}|http[s]?://|\b\d{3}-\d{8}\b", data["reply"])
    assert "已为您转接" not in data["reply"]
    assert "工单" not in data["reply"]
    assert len(data["suggestions"]) == 6


# ---------- 10. 首屏欢迎语接口 ----------


def test_welcome_endpoint_is_read_only(client):
    before = client.get("/api/sessions").json()
    assert before == []

    resp = client.get("/api/chat/welcome")
    assert resp.status_code == 200
    data = resp.json()
    assert data["reply"] == GREETING_TEXT
    assert data["reply_type"] == "greeting"
    assert len(data["suggestions"]) == 6

    # 反复调用不能留下会话或消息（这是首屏接口，刷新多少次都该干净）
    client.get("/api/chat/welcome")
    assert client.get("/api/sessions").json() == []


def test_welcome_suggestions_shape():
    items = default_suggestions()
    assert len(items) == 6
    labels = [i["label"] for i in items]
    assert labels == ["物流配送", "退款政策", "退换货", "售后服务", "订单查询", "联系人工客服"]
    for item in items:
        assert item["label"].strip()
        assert item["query"].strip()
        assert item["description"].strip()
        # label 是按钮上的短标题，query 是真正发给后端的问句，两者职责不同
        assert len(item["query"]) >= len(item["label"])
    # query 不能重复，否则两个按钮会问同一件事
    assert len({i["query"] for i in items}) == 6


def test_default_suggestions_returns_copies():
    """返回副本：调用方改了不该污染模块级常量。"""
    first = default_suggestions()
    first[0]["label"] = "被改了"
    assert default_suggestions()[0]["label"] == DEFAULT_SUGGESTIONS[0]["label"]


# ---------- 11. 快捷问题必须真的能通到真实链路 ----------


@pytest.mark.parametrize("query", [item["query"] for item in DEFAULT_SUGGESTIONS])
def test_each_suggestion_reaches_a_real_path(client, indexed_doc, query):
    """把每个快捷问题的 query 原样提交给聊天接口 —— 这正是前端点击时发生的事。

    允许的结果只有两种：
      * knowledge / no_answer —— 进了知识库检索（有资料就给原文，没资料就诚实说没有）；
      * human_service         —— 走能力说明。
    绝不允许落到 fallback / unclear，那意味着按钮点完只是换一句“我不懂”。
    """
    data = ask(client, query)
    assert data["reply_type"] not in OFF_TOPIC, f"快捷问题 {query!r} 落到了 {data['reply_type']}"
    assert data["reply_type"] in {"knowledge", "no_answer", "human_service"}
    assert data["retrieval"]["reason"] != "skipped_smalltalk" or data["reply_type"] == "human_service"


def test_suggestion_queries_are_not_off_scope():
    """纯规则层：快捷问题不可能是“无关问题”。"""
    for item in DEFAULT_SUGGESTIONS:
        match = match_smalltalk(item["query"])
        assert match is None or match.kind == "human_service", item["query"]


# ---------- 12. 一次请求只产生两条消息（不会重复发送） ----------


def test_one_request_creates_exactly_one_user_and_one_assistant_message(client, indexed_doc):
    data = ask(client, "你好", session_id=None)
    session_id = data["session_id"]

    msgs = client.get(f"/api/sessions/{session_id}/messages").json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["content"] == "你好"
    assert msgs[1]["content"] == GREETING_TEXT
    # reply_type 要落库，否则刷新页面后前端就不知道这是问候还是知识库原文
    assert msgs[1]["reply_type"] == "greeting"


def test_reply_type_persisted_in_history(client, indexed_doc):
    data = ask(client, "退款一般几天到账？")
    msgs = client.get(f"/api/sessions/{data['session_id']}/messages").json()
    assert msgs[-1]["reply_type"] == "knowledge"
    assert msgs[-1]["sources"]


def test_conversation_and_business_share_one_session(client, indexed_doc):
    """同一会话里先问候再问业务，两条回复各自带正确的 reply_type。"""
    first = ask(client, "你好")
    second = ask(client, "退款几天到账", session_id=first["session_id"])
    assert second["session_id"] == first["session_id"]

    msgs = client.get(f"/api/sessions/{first['session_id']}/messages").json()
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert [m["reply_type"] for m in msgs] == [None, "greeting", None, "knowledge"]


# ---------- 13. 纯知识库模式下，引导链路同样零外联 ----------


def test_conversation_path_makes_no_external_request(client, indexed_doc, monkeypatch, no_network):
    # 环境里塞一个真 Key：旧实现会在这里偷偷调用模型
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test-abcd1234efgh5678ijkl")

    for message in ["你好", "你是谁", "谢谢", "再见", "今天天气怎么样", "我想联系人工客服", "？？？"]:
        data = ask(client, message)
        assert data["answer_mode"] == "knowledge_only"
        assert data["degraded"] is None

    assert no_network == [], f"引导链路发生了外联尝试：{no_network}"


def test_business_path_makes_no_external_request(client, indexed_doc, monkeypatch, no_network):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test-abcd1234efgh5678ijkl")
    data = ask(client, "你好，我想退款")
    assert data["reply_type"] == "knowledge"
    assert no_network == [], f"业务链路发生了外联尝试：{no_network}"


# ---------- 14. 客套前缀剥离（让“你好，我想退款”命中退款的真正原因） ----------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("你好，我想退款", "退款"),
        ("您好，我想知道退款流程", "退款流程"),
        ("请问一下退货怎么操作", "退货怎么操作"),
        ("麻烦帮我查一下订单", "订单"),
        ("我想查询订单", "订单"),
    ],
)
def test_strip_request_prefix(raw, expected):
    assert strip_request_prefix(raw) == expected


def test_strip_prefix_never_returns_empty():
    """只发一句客套时不能给检索一个空串。"""
    assert strip_request_prefix("请问") == "请问"
    assert strip_request_prefix("   ") == ""


# ---------- 15. 会话与历史不受影响（回归） ----------


def test_session_history_and_delete_still_work(client, indexed_doc):
    data = ask(client, "谢谢")
    sid = data["session_id"]

    assert any(s["id"] == sid for s in client.get("/api/sessions").json())

    assert client.delete(f"/api/sessions/{sid}").status_code == 204
    assert client.get("/api/sessions").json() == []
