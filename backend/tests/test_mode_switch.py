"""回答模式切换测试。

这组测试要证明的不是"接口能返回 200"，而是四件事：

1. 切换**真的改变了后端行为**，不是前端改个字；
2. 切换是**持久化**的，重启后仍在（模拟：清内存 → 从库重载）；
3. knowledge_only 下**任何路径**都不会外联，即使环境里有 Key；
4. 模型失败（402 / 未配置）时既不编造回答，也不谎称"模型可用"。
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.llm import status as llm_status
from app.rag.answer import NO_KB_ANSWER
from app.runtime_mode import effective_answer_mode, reset_override
from app.services import chat_service, settings_service
from tests.support import FakeLLM, QuotaLLM


def get_mode(client) -> dict:
    resp = client.get("/api/settings/answer-mode")
    assert resp.status_code == 200, resp.text
    return resp.json()


def put_mode(client, mode: str) -> dict:
    resp = client.put("/api/settings/answer-mode", json={"mode": mode})
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------- 1. 读取 ----------
def test_read_default_mode(client):
    data = get_mode(client)
    assert data["mode"] == "knowledge_only"
    assert data["scope"] == "global"
    assert data["overridden"] is False
    assert data["default_mode"] == "knowledge_only"
    values = [o["value"] for o in data["options"]]
    assert values == ["knowledge_only", "llm"]
    for option in data["options"]:
        assert option["label"] and option["description"]
    # 测试环境没有密钥
    assert data["model"]["configured"] is False
    assert data["model"]["status"] == "not_configured"
    assert data["model"]["will_be_called"] is False


def test_mode_payload_never_leaks_key(client, monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-secret-should-never-appear")
    raw = client.get("/api/settings/answer-mode").text
    assert "sk-secret" not in raw
    assert "api_key" not in raw.lower()
    data = get_mode(client)
    assert data["model"]["configured"] is True
    assert data["model"]["status"] == "unverified"


# ---------- 2. 切换真的生效 ----------
def test_switch_to_llm_changes_backend_behaviour(client, indexed_doc, monkeypatch):
    fake = FakeLLM(reply="这是模型组织后的回答。")
    monkeypatch.setattr(chat_service, "get_llm_client", lambda: fake)
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test-1234")

    before = client.post("/api/chat", json={"message": "退款一般几天到账"}).json()
    assert before["answer_mode"] == "knowledge_only"
    assert fake.calls == [], "知识库模式不应调用模型"

    data = put_mode(client, "llm")
    assert data["mode"] == "llm"
    assert data["model"]["will_be_called"] is True

    after = client.post("/api/chat", json={"message": "退款一般几天到账"}).json()
    assert after["answer_mode"] == "llm"
    # 退款意图会追加“未接入退款系统”的提示，所以只断言模型内容在开头
    assert after["answer"].startswith(fake.reply)
    assert fake.calls, "切到 llm 后必须真的调用模型"


def test_switch_back_to_knowledge_only_stops_calling(client, indexed_doc, monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test-1234")
    put_mode(client, "llm")
    put_mode(client, "knowledge_only")

    def explode():
        raise AssertionError("知识库模式不应获取模型客户端")

    monkeypatch.setattr(chat_service, "get_llm_client", explode)
    data = client.post("/api/chat", json={"message": "退款一般几天到账"}).json()
    assert data["answer_mode"] == "knowledge_only"
    assert data["degraded"] is None
    assert data["sources"]


def test_invalid_mode_rejected(client):
    resp = client.put("/api/settings/answer-mode", json={"mode": "gpt-4"})
    assert resp.status_code == 422
    assert "不支持的运行模式" in resp.json()["detail"]
    # 非法写入不能改变实际模式
    assert get_mode(client)["mode"] == "knowledge_only"


# ---------- 3. 持久化 ----------
def test_mode_survives_restart(client, db):
    put_mode(client, "llm")
    assert get_mode(client)["mode"] == "llm"

    # 模拟进程重启：清空内存缓存，再从数据库重新加载
    reset_override()
    assert effective_answer_mode() == "knowledge_only"  # 内存已清

    settings_service.load_answer_mode(db)
    assert effective_answer_mode() == "llm"
    assert get_mode(client)["mode"] == "llm"


def test_reset_returns_to_env_default(client):
    put_mode(client, "llm")
    data = client.post("/api/settings/answer-mode/reset").json()
    assert data["mode"] == "knowledge_only"
    assert data["overridden"] is False


# ---------- 4. 健康检查如实上报 ----------
def test_health_reports_effective_mode(client):
    assert client.get("/api/health").json()["answer_mode"] == "knowledge_only"
    put_mode(client, "llm")
    health = client.get("/api/health").json()
    assert health["answer_mode"] == "llm"
    assert health["llm"]["mode"] == "llm"
    assert health["llm"]["source"] == "runtime"


# ---------- 5. 未配置模型时不外联、不编造 ----------
def test_llm_mode_without_key_degrades_without_network(client, indexed_doc, no_network):
    put_mode(client, "llm")
    data = client.post("/api/chat", json={"message": "退款一般几天到账"}).json()

    assert data["answer_mode"] == "llm"
    assert data["degraded"] == "llm_not_configured"
    assert data["answer_kind"] == "llm_degraded"
    # 降级只能陈列检索原文，不能凭空生成
    assert data["sources"]
    assert no_network == [], f"未配置密钥却尝试外联：{no_network}"

    model = get_mode(client)["model"]
    # 没配密钥时，最准确的状态是“未配置”，而不是含糊的“模型不可用”
    assert model["status"] == "not_configured"
    assert "配置" in model["status_text"]
    assert model["will_be_called"] is False


def test_llm_mode_without_context_says_not_found(client, indexed_doc):
    put_mode(client, "llm")
    data = client.post("/api/chat", json={"message": "今天天气怎么样"}).json()
    assert data["answer"].startswith(NO_KB_ANSWER) or data["reply_type"] in {
        "fallback",
        "no_answer",
    }
    assert data["sources"] == []


# ---------- 6. 402 余额不足 ----------
def test_quota_exceeded_is_reported_honestly(client, indexed_doc, monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test-1234")
    put_mode(client, "llm")
    monkeypatch.setattr(chat_service, "get_llm_client", lambda: QuotaLLM())

    data = client.post("/api/chat", json={"message": "退款一般几天到账"}).json()
    assert data["degraded"] == "llm_quota_exceeded"
    assert "余额不足" in data["answer"]
    assert data["sources"], "降级时必须给出知识库原文，而不是空回答"

    model = get_mode(client)["model"]
    assert model["status"] == "error"
    assert "余额" in model["status_text"] or "402" in model["status_text"]


def test_success_clears_previous_failure(client, indexed_doc, monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test-1234")
    put_mode(client, "llm")

    monkeypatch.setattr(chat_service, "get_llm_client", lambda: QuotaLLM())
    client.post("/api/chat", json={"message": "退款一般几天到账"})
    assert get_mode(client)["model"]["status"] == "error"

    monkeypatch.setattr(chat_service, "get_llm_client", lambda: FakeLLM())
    client.post("/api/chat", json={"message": "退款一般几天到账"})
    assert get_mode(client)["model"]["status"] == "ok"
    assert get_mode(client)["model"]["last_failure"] is None


# ---------- 7. 切换不清空会话 ----------
def test_switching_mode_keeps_sessions_and_messages(client, indexed_doc):
    first = client.post("/api/chat", json={"message": "退款一般几天到账"}).json()
    sid = first["session_id"]

    put_mode(client, "llm")
    put_mode(client, "knowledge_only")

    msgs = client.get(f"/api/sessions/{sid}/messages").json()
    assert len(msgs) == 2
    assert msgs[0]["content"] == "退款一般几天到账"


# ---------- 8. 状态快照的边界 ----------
def test_status_snapshot_counts():
    llm_status.reset()
    assert llm_status.snapshot()["failures"] == 0
    llm_status.record_failure("llm_timeout")
    snap = llm_status.snapshot()
    assert snap["failures"] == 1
    assert snap["last_failure"]["code"] == "llm_timeout"
    assert "超时" in snap["last_failure"]["text"]
    llm_status.record_success()
    assert llm_status.snapshot()["last_failure"] is None


@pytest.mark.parametrize("mode", ["KNOWLEDGE_ONLY", " llm ", "LLM"])
def test_mode_value_is_normalized(client, mode):
    data = put_mode(client, mode)
    assert data["mode"] in {"knowledge_only", "llm"}
