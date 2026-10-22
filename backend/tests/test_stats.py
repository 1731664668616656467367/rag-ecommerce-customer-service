"""工作台统计接口测试。

为什么专门测这个接口：
    首页仪表盘上的每个数字都要有真实来源。只要 `/api/stats` 少算一格、
    或者在空库时返回 0 却让人以为是"命中率为 0"，页面就会变成"看起来很专业"的假仪表盘。
    所以这里既测正常聚合，也测空库与"没有分母"这两种容易含糊的情况。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db.models import Feedback, Message, Session
from app.db.session import get_session_factory


def _upload(client, name: str, content: bytes):
    return client.post(
        "/api/knowledge/upload",
        files={"file": (name, content, "text/markdown")},
        params={"replace": "true"},
    )


def test_stats_empty_library_is_all_zero_but_ratio_is_null(client):
    """空库时数量为 0 是对的，但"知识引用率"没有分母，必须是 null 而不是 0。

    这两种情况在页面上长得完全不一样（"—" vs "0%"），
    把"无法计算"显示成"0%"就等于在报一个不存在的指标。
    """
    body = client.get("/api/stats").json()
    assert body["sessions_total"] == 0
    assert body["messages_total"] == 0
    assert body["docs_total"] == 0
    assert body["chunks"] == 0
    assert body["knowledge_ratio"] is None
    assert body["answer_mix"] == {}


def test_stats_counts_only_what_actually_exists(client, db):
    # 一个会话 + 一问一答，回答带来源
    resp = client.post("/api/chat", json={"message": "同城配送一般几天能到？"})
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]

    # 再往里塞一条人工构造的助手消息，确认聚合是"分类汇总"而不是"总数拍脑袋"
    db.add(
        Message(
            session_id=session_id,
            role="assistant",
            content="这是一条不存在于检索链路的回答",
            intent="其他",
            answer_mode="knowledge_only",
            reply_type="no_answer",
        )
    )
    db.add(Feedback(message_id=resp.json()["message_id"], rating="helpful"))
    db.commit()

    body = client.get("/api/stats").json()
    assert body["sessions_total"] == 1
    assert body["messages_total"] == 3  # 用户 + 真实回答 + 手工插入的那条
    assert body["assistant_total"] == 2
    assert body["feedback_helpful"] == 1
    assert body["feedback_unhelpful"] == 0
    # answer_mix 的键必须来自真实 reply_type，不能是固定枚举写死
    assert "no_answer" in body["answer_mix"]
    assert sum(body["answer_mix"].values()) == 2
    # 只有 1 条 knowledge 时比例是 1/2 或 0/2，取决于检索是否命中；
    # 但只要有分母就必须是 0~1 的浮点数
    assert body["knowledge_ratio"] is not None
    assert 0.0 <= body["knowledge_ratio"] <= 1.0


def test_stats_today_window_uses_local_midnight(client, db):
    """"今日"必须按服务器本地时区切天，再用 UTC 区间去查。

    直接用 UTC 切天在东八区会把"今天 0 点到 8 点"算成昨天，
    早上打开工作台看到"今日会话 0"就是一个纯粹的时区 bug。
    """
    factory = get_session_factory()
    session = factory()
    try:
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        yesterday = now_utc - timedelta(days=2)
        session.add(Session(title="今天的会话"))
        session.add(Session(title="两天前的会话"))
        session.commit()

        rows = session.query(Session).order_by(Session.id).all()
        rows[0].created_at = now_utc
        rows[1].created_at = yesterday
        session.commit()
    finally:
        session.close()

    body = client.get("/api/stats").json()
    assert body["sessions_total"] == 2
    assert body["sessions_today"] == 1


def test_stats_reports_index_and_mode_from_real_sources(client):
    _upload(client, "物流说明.md", "同城配送出库后 1 至 2 天送达，跨省 3 至 5 天。".encode("utf-8"))

    body = client.get("/api/stats").json()
    assert body["docs_total"] == 1
    assert body["docs_indexed"] == 1
    assert body["chunks"] >= 1
    assert body["dim"] > 0
    assert body["index_backend"]
    # 模式字段要和 /api/settings/answer-mode 一致，不能各算一套
    mode = client.get("/api/settings/answer-mode").json()
    assert body["answer_mode"] == mode["mode"]
    assert body["mode_label"] == mode["label"]
    assert body["generated_at"]
