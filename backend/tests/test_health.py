"""健康检查测试。"""

from __future__ import annotations


def test_health_returns_structured_status(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] in ("ok", "degraded")
    assert data["database"] == "ok"
    assert data["embedding"]["provider"] == "local-hashing"
    assert data["answer_mode"] == "knowledge_only"
    # 纯知识库模式：没配密钥是正常状态，不应该被当成故障
    assert data["llm"]["configured"] is False
    assert data["llm"]["will_be_called"] is False
    assert not any("DEEPSEEK_API_KEY" in w for w in data["warnings"])
    assert isinstance(data["warnings"], list)


def test_health_reports_index_stats(client):
    data = client.get("/api/health").json()
    assert data["index"]["chunks"] == 0
    assert data["index"]["backend"] in ("numpy", "faiss")
    # 检索方式也必须如实暴露
    assert data["retrieval"]["mode"] == "hybrid"
    assert "vector" in data["retrieval"]["channels"]
    assert "bm25" in data["retrieval"]["channels"]


def test_root_route(client):
    assert client.get("/").status_code == 200
