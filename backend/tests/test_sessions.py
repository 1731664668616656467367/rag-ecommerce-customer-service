"""会话与消息持久化测试：创建、历史、隔离、删除、重启后仍存在。"""

from __future__ import annotations

from sqlalchemy import select

from app.db.models import Message, Session
from app.db.session import get_session_factory
from app.services import chat_service, session_service
from tests.support import FakeLLM


def test_create_and_list_sessions(client):
    created = client.post("/api/sessions", json={"title": "退货咨询"})
    assert created.status_code == 201
    sid = created.json()["id"]

    listing = client.get("/api/sessions").json()
    assert any(s["id"] == sid for s in listing)
    assert listing[0]["title"] == "退货咨询"


def test_create_session_without_body(client):
    resp = client.post("/api/sessions")
    assert resp.status_code == 201
    assert resp.json()["title"] == "新会话"


def test_messages_persist_and_are_ordered(client, indexed_doc, monkeypatch, llm_mode):
    monkeypatch.setattr(chat_service, "get_llm_client", lambda: FakeLLM(reply="回答一"))
    first = client.post("/api/chat", json={"message": "第一个问题：退款多久到账"}).json()

    monkeypatch.setattr(chat_service, "get_llm_client", lambda: FakeLLM(reply="回答二"))
    client.post(
        "/api/chat",
        json={"message": "第二个问题：物流多久到", "session_id": first["session_id"]},
    )

    msgs = client.get(f"/api/sessions/{first['session_id']}/messages").json()
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert msgs[0]["content"].startswith("第一个问题")
    # 退款意图会自动附加“未接入退款系统”的提示，所以用 startswith
    assert msgs[1]["content"].startswith("回答一")
    assert msgs[2]["content"].startswith("第二个问题")
    # 会话标题被首条问题自动命名
    assert "第一个问题" in first["session_title"]


def test_messages_of_unknown_session_404(client):
    assert client.get("/api/sessions/nope/messages").status_code == 404


def test_delete_session_cascades_messages(db, client, indexed_doc):
    sid = client.post("/api/sessions", json={}).json()["id"]
    client.post("/api/chat", json={"message": "退款多久到账", "session_id": sid})
    assert db.scalars(select(Message).where(Message.session_id == sid)).all()

    assert client.delete(f"/api/sessions/{sid}").status_code == 204
    assert client.get(f"/api/sessions/{sid}/messages").status_code == 404

    db.expire_all()
    assert db.scalars(select(Message).where(Message.session_id == sid)).all() == []
    assert db.get(Session, sid) is None


def test_delete_unknown_session_404(client):
    assert client.delete("/api/sessions/not-exist").status_code == 404


def test_context_isolation_between_sessions(db, indexed_doc):
    s1 = session_service.create_session(db, "会话一")
    s2 = session_service.create_session(db, "会话二")
    session_service.add_message(db, s1.id, "user", "会话一的私密问题")
    session_service.add_message(db, s2.id, "user", "会话二的其他问题")

    h1 = session_service.recent_history(db, s1.id)
    h2 = session_service.recent_history(db, s2.id)
    assert len(h1) == 1 and h1[0]["content"] == "会话一的私密问题"
    assert len(h2) == 1 and h2[0]["content"] == "会话二的其他问题"


def test_history_from_database_not_memory(db, indexed_doc):
    """模拟进程重启：新建一个 Session 对象（不复用旧对象）重新读库。"""
    sid = session_service.create_session(db, "重启测试").id
    session_service.add_message(db, sid, "user", "重启前的消息")
    db.close()

    fresh = get_session_factory()()
    try:
        msgs = session_service.list_messages(fresh, sid)
        assert [m.content for m in msgs] == ["重启前的消息"]
    finally:
        fresh.close()


def test_history_window_limits_context(db):
    sid = session_service.create_session(db).id
    for i in range(12):
        session_service.add_message(db, sid, "user", f"第{i}条")
    hist = session_service.recent_history(db, sid, window=4)
    assert len(hist) == 4
    assert hist[-1]["content"] == "第11条"


def test_feedback_flow(db, client, indexed_doc, monkeypatch, llm_mode):
    import app.services.chat_service as cs

    monkeypatch.setattr(cs, "get_llm_client", lambda: FakeLLM(reply="退款需1-3个工作日。"))
    data = client.post("/api/chat", json={"message": "退款多久到账"}).json()

    resp = client.post(
        "/api/feedback", json={"message_id": data["message_id"], "rating": "helpful"}
    )
    assert resp.status_code == 201
    assert resp.json()["rating"] == "helpful"


def test_feedback_invalid_rating(client):
    resp = client.post("/api/feedback", json={"message_id": "abcd1234", "rating": "great"})
    assert resp.status_code == 422


def test_feedback_unknown_message_404(client):
    resp = client.post(
        "/api/feedback", json={"message_id": "doesnotexist", "rating": "helpful"}
    )
    assert resp.status_code == 404
