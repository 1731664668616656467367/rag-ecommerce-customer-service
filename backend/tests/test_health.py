"""健康检查测试。"""

from __future__ import annotations


def test_health_returns_structured_status(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] in ("ok", "degraded")
    assert data["database"] == "ok"
    assert data["embedding"]["provider"] == "local-hashing"
    assert data["llm"]["configured"] is False
    assert isinstance(data["warnings"], list)
    # 未配置密钥时必须明确告警，不能假装一切正常
    assert any("DEEPSEEK_API_KEY" in w for w in data["warnings"])


def test_health_reports_index_stats(client):
    data = client.get("/api/health").json()
    assert data["index"]["chunks"] == 0
    assert data["index"]["backend"] in ("numpy", "faiss")


def test_root_route(client):
    assert client.get("/").status_code == 200
