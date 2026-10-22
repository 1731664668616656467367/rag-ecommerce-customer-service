"""纯知识库模式（knowledge_only）专项测试。

核心不是“代码里没写调用”，而是**主动拦截网络**：
patch 掉 socket.connect / socket.create_connection / httpx 的 send，
只要有任何外联尝试就会立刻失败。这样“不调用 DeepSeek”是被证明的，不是被声称的。
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.customer_service.conversation_rules import OFF_SCOPE_TEXT
from app.rag.answer import NO_KB_ANSWER
from app.rag.lexical import BM25Index, CorpusStats, coverage, tokenize
from app.rag.retriever import Retriever
from app.rag.vector_store import VectorIndex
from app.services import chat_service, session_service
from tests.support import FakeLLM

# no_network 拦截器已上移到 conftest.py：对话引导测试也要用它，
# 两处各写一份迟早会只改一处，留下一个假的“通过”。


# ---------- 1. 有 Key 也不外联 ----------
def test_no_external_request_even_with_api_key(client, indexed_doc, monkeypatch, no_network):
    # 模拟“环境变量里真的有 Key”，这是旧实现会偷偷调用模型的场景
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test-abcd1234efgh5678ijkl")
    assert settings.llm_configured is True
    assert settings.llm_enabled is False

    resp = client.post("/api/chat", json={"message": "退款一般几天到账？"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["answer_mode"] == "knowledge_only"
    assert data["degraded"] is None
    assert data["sources"]
    assert no_network == [], f"发生了意外的外联尝试：{no_network}"


def test_network_guard_would_catch_a_real_call(client, indexed_doc, monkeypatch, llm_mode, no_network):
    """反向对照：证明上面的拦截器不是摆设 —— llm 模式下确实会尝试外联并被拦下。"""
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test-abcd1234efgh5678ijkl")
    data = client.post("/api/chat", json={"message": "退款一般几天到账？"}).json()

    assert no_network, "拦截器没有记录到任何请求，说明它根本没生效"
    assert data["degraded"] == "llm_unavailable"
    # 降级时只能展示知识库原文，不能凭空生成
    assert data["answer_kind"] == "llm_degraded"


# ---------- 2. 完全不获取模型客户端 ----------
def test_chat_never_requests_llm_client(client, indexed_doc, monkeypatch):
    def explode():
        raise AssertionError("knowledge_only 模式不应获取大模型客户端")

    monkeypatch.setattr(chat_service, "get_llm_client", explode)
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test-abcd1234efgh5678ijkl")

    resp = client.post("/api/chat", json={"message": "同城配送几天能到？"})
    assert resp.status_code == 200


# ---------- 3. 意图识别纯本地 ----------
async def test_intent_ignores_llm_in_knowledge_mode():
    spy = FakeLLM(intent_reply='{"intent":"退款"}')
    result = await chat_service.classify_intent("东西有点问题", spy)
    assert spy.calls == []
    assert result["method"] != "llm"


async def test_handle_chat_ignores_injected_client(db, indexed_doc):
    """即使调用方硬塞一个客户端，也不会被调用（防御性设计）。"""
    spy = FakeLLM(reply="不该出现")
    result = await chat_service.handle_chat(db, "退款几天到账", llm=spy)
    assert spy.calls == []
    assert result["answer_mode"] == "knowledge_only"
    assert result["answer"] != "不该出现"


# ---------- 4. 命中知识库 ----------
def test_hit_returns_excerpt_and_source(client, indexed_doc):
    data = client.post("/api/chat", json={"message": "退款一般几天到账？"}).json()
    assert data["retrieval"]["has_context"] is True
    assert data["sources"][0]["file_name"] == "退换货政策.md"
    assert "原文摘录" in data["answer"]
    # 必须真的包含知识库里的数字，而不是编造
    assert "1 至 3 个工作日" in data["answer"]
    assert data["answer_kind"] == "knowledge_extract"


# ---------- 5. 无关问题不当作可靠答案 ----------
@pytest.mark.parametrize(
    "question", ["火星探测器什么时候发射", "今天天气怎么样", "你们老板是谁"]
)
def test_unrelated_question_gets_fixed_prompt(client, indexed_doc, question):
    """无关问题必须如实说“答不了”，并且不能把检索到的片段伪装成答案。

    行为在本轮有调整：以前统一回“暂未找到可靠信息”，现在改成明确说明服务范围
    （reply_type=fallback）并附上常见问题入口。断言的重点没变——没有来源、
    不能出现知识库里别处的具体条款，也不能编造。
    """
    data = client.post("/api/chat", json={"message": question}).json()
    assert data["retrieval"]["has_context"] is False
    assert data["sources"] == []
    assert data["reply_type"] in {"fallback", "no_answer"}
    assert "1 至 3 个工作日" not in data["answer"]
    # 两种话术都必须明确告知“没找到”，不能让用户以为这就是答案
    assert data["answer"] in {OFF_SCOPE_TEXT, NO_KB_ANSWER} or data["answer"].startswith(NO_KB_ANSWER)


def test_unknown_subject_is_not_answered_by_topic_word(client, db):
    """回归用例：问句里只撞上“配送”两个字，不等于知识库回答了这个问题。

    “你们支持火星配送吗？”曾经命中《02-配送与物流时效》，把整段配送范围搬出来当答案。
    差别在于：知识库里有“配送”，但从没出现过“火星”。

    这里刻意放了 5 篇文档（接近真实知识库规模）而不是 1 篇：
    “配送”在这份语料里是跨文档的常见词，“火星”一次都没出现——这个差别
    只有在语料有一定规模时才统计得出来。只有 2 个片段时每个词都同样稀有，
    这件事本就无从判断。如果哪天有人把门槛调松，这条会第一时间失败。
    """
    from app.services import knowledge_service

    docs = {
        "01-退换货政策.md": (
            "# 退换货政策\n\n"
            "自签收之日起 7 个自然日内，商品未使用且不影响二次销售的，可申请无理由退货。\n\n"
            "定制类商品与贴身衣物不支持无理由退货。商品存在质量问题的，自签收之日起 15 日内可申请退货，"
            "30 日内可申请换货；退货寄回的运费按配送时的实际收费结算。\n"
        ),
        "02-配送与物流时效.md": (
            "# 配送与物流时效\n\n"
            "同城配送一般 1 至 2 天送达，跨省配送一般 3 至 5 天，偏远地区顺延。\n\n"
            "配送范围覆盖全国大部分地区，中国港澳台地区及海外国家暂不支持直邮。\n"
        ),
        "03-订单查询与修改.md": (
            "# 订单查询与修改\n\n"
            "订单发货前可在订单详情页修改收货地址，发货后请联系客服协助处理。\n\n"
            "电子发票在订单完成后 1 个工作日内开具，可在订单详情页下载。\n"
        ),
        "04-售后与保修.md": (
            "# 售后与保修\n\n"
            "商品保修期为 12 个月，保修范围内免费维修，人为损坏需自费。\n\n"
            "保修不支持跨地区转移，二次销售的商品不享受保修服务。\n"
        ),
        "05-会员与优惠券.md": (
            "# 会员与优惠券\n\n"
            "会员积分可在下单时抵扣现金，优惠券与积分不可叠加使用。\n\n"
            "优惠券不支持兑换现金，过期后自动失效。\n"
        ),
    }
    for name, text in docs.items():
        knowledge_service.add_document(db, name, text.encode("utf-8"))

    hit = client.post("/api/chat", json={"message": "同城配送一般几天能到？"}).json()
    assert hit["retrieval"]["has_context"] is True
    assert hit["sources"][0]["file_name"] == "02-配送与物流时效.md"

    miss = client.post("/api/chat", json={"message": "你们支持火星配送吗？"}).json()
    assert miss["retrieval"]["has_context"] is False
    assert miss["sources"] == []
    assert miss["answer"].startswith(NO_KB_ANSWER)
    # 没有摘录就不能标成“知识库原文”，否则前端会给出错误的来源标签
    assert miss["answer_kind"] == "no_answer"


def test_weighted_coverage_punishes_unknown_words():
    """语料里从没出现过的词，不该因为“碰巧撞上一个话题词”就被算作命中。"""
    stats = CorpusStats(
        [
            "同城配送一般 1 至 2 天送达",
            "配送范围覆盖全国大部分地区",
            "退款将在 1 至 3 个工作日内发起",
        ]
    )
    body = "配送范围覆盖全国大部分地区"
    # 问题里的关键词“火星”语料中不存在，只撞上“配送”，不该算有依据
    assert stats.weighted_coverage("你们支持火星配送吗？", body) < 0.2
    # 问题里的词基本都在片段中出现 -> 高覆盖
    assert stats.weighted_coverage("配送范围", body) > 0.9
    # 未登录词权重恒为 1.0，出现过的词按频率衰减；这条性质不随语料规模变化
    assert stats.term_weight("火星") == 1.0
    assert stats.term_weight("配送") == 1.0 / 3  # 出现在 2 个片段里
    assert stats.term_weight("配送") < stats.term_weight("火星")


# ---------- 6. 知识库为空 ----------
def test_empty_knowledge_base_still_answers(client):
    data = client.post("/api/chat", json={"message": "退款几天到账"}).json()
    assert data["retrieval"]["reason"] == "empty_index"
    assert data["answer"] == NO_KB_ANSWER + "\n\n" + chat_service.BUSINESS_DATA_NOTICE["退款"]
    assert data["sources"] == []


# ---------- 7. 模型不可用不影响纯知识库问答 ----------
def test_deepseek_outage_does_not_affect_knowledge_mode(client, indexed_doc, monkeypatch):
    """即使 DeepSeek 客户端一构造就炸，纯知识库模式也照常回答。"""
    import app.llm.deepseek_client as real_client

    class ExplodingClient(real_client.DeepSeekClient):
        def __init__(self, *a, **kw):
            raise AssertionError("不应构造 DeepSeek 客户端")

    monkeypatch.setattr(real_client, "DeepSeekClient", ExplodingClient)
    data = client.post("/api/chat", json={"message": "退款几天到账"}).json()
    assert data["retrieval"]["has_context"] is True
    assert data["answer_kind"] == "knowledge_extract"


# ---------- 8. 删除文档后不再返回 ----------
def test_deleted_document_is_not_retrievable(client, db):
    from app.services import knowledge_service

    doc = knowledge_service.add_document(
        db, "临时政策.md", "临时活动：满 300 元减 50 元，活动截止 12 月 31 日。".encode("utf-8")
    )
    first = client.post("/api/chat", json={"message": "满300减50活动截止到什么时候"}).json()
    assert any(s["document_id"] == doc.id for s in first["sources"])

    assert client.delete(f"/api/knowledge/{doc.id}").status_code == 204
    second = client.post("/api/chat", json={"message": "满300减50活动截止到什么时候"}).json()
    assert all(s["document_id"] != doc.id for s in second["sources"])
    assert "12 月 31 日" not in second["answer"]


# ---------- 9. 会话与数据库仍正常 ----------
def test_sessions_and_history_still_work(client, indexed_doc):
    first = client.post("/api/chat", json={"message": "退款几天到账"}).json()
    client.post(
        "/api/chat",
        json={"message": "同城配送几天能到", "session_id": first["session_id"]},
    )
    msgs = client.get(f"/api/sessions/{first['session_id']}/messages").json()
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    # 每条助手消息都记录了产生方式，前端才能如实标注
    assert all(m["answer_mode"] == "knowledge_only" for m in msgs if m["role"] == "assistant")


def test_message_stores_answer_mode(db, indexed_doc):
    sid = session_service.create_session(db).id
    msg = session_service.add_message(
        db, sid, "assistant", "内容", intent="退款", answer_mode="knowledge_only"
    )
    assert msg.answer_mode == "knowledge_only"


# ---------- 10. 健康检查如实反映模式与检索方式 ----------
def test_health_reports_mode_and_channels(client):
    data = client.get("/api/health").json()
    assert data["answer_mode"] == "knowledge_only"
    assert data["llm"]["enabled"] is False
    assert data["llm"]["will_be_called"] is False
    # 术语在 UI 改版时统一为“知识库模式 / 大语言模型模式”（原“纯知识库模式”）
    assert "知识库模式" in data["llm"]["note"]
    assert data["llm"]["source"] == "env"
    assert data["retrieval"]["mode"] == "hybrid"
    assert data["retrieval"]["channels"] == ["vector", "bm25"]


# ---------- 11. 检索可插拔：单独通道也能工作 ----------
def test_vector_only_mode(indexed_doc):
    result = Retriever(mode="vector").retrieve("退款几天到账")
    assert result.methods == ["vector"]
    assert result.has_context is True


def test_lexical_only_mode(indexed_doc):
    result = Retriever(mode="lexical").retrieve("退款几天到账")
    assert result.methods == ["bm25"]
    assert result.has_context is True
    assert result.hits[0].file_name == "退换货政策.md"


def test_bm25_and_tokenizer_units():
    tokens = tokenize("退款 3 个工作日 Refund")
    assert "退款" in tokens and "refund" in tokens
    assert coverage("退款几天到账", "退款将在 1 至 3 个工作日内发起") >= 0.2
    assert coverage("火星探测器", "退款将在 1 至 3 个工作日内发起") == 0

    index = BM25Index(["退款三个工作日到账", "物流同城次日达"])
    hits = index.search("退款多久")
    assert hits and hits[0].index == 0


# ---------- 12. embedding 变更后可检测出需要重建索引 ----------
def test_index_signature_mismatch_requires_reindex(tmp_path):
    from app.rag.embeddings import LocalHashingEmbedder

    idx = VectorIndex(index_dir=tmp_path)
    emb = LocalHashingEmbedder(dim=64)
    idx.upsert_document("d1", "a.md", ["退款三个工作日"], emb.embed(["退款三个工作日"]), signature="a:64")

    with pytest.raises(ValueError, match="重建索引"):
        idx.upsert_document("d2", "b.md", ["物流次日达"], emb.embed(["物流次日达"]), signature="b:64")
