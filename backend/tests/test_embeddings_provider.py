"""Embedding provider 的选择、真实维度与索引重建安全性。

这些用例要回答的问题很具体：
    1. 切了 EMBEDDING_PROVIDER，代码**真的**去调 Ollama 了吗？还是只改了状态页文字？
    2. 维度是服务真实返回的，还是被本地哈希的 4096 顶替了？
    3. Ollama 不在时，知识库还能不能用（不能因为降级就整库失效）？
    4. 重建索引中途失败，会不会把线上旧索引毁掉？

关于“假 Ollama”：
    用一个真实监听端口的 HTTP 服务实现 /api/tags 与 /api/embed 协议，
    被测代码走的是和线上完全一样的 httpx 请求路径——不是 monkeypatch 掉 embed 方法。
    这样“真的发出请求”这件事本身也被验证了（断言 hit 计数）。
"""

from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pytest

EMBED_DIM = 1024  # bge-m3 的真实维度；刻意不等于本地哈希的 4096


def _fake_vector(text: str, dim: int = EMBED_DIM) -> list[float]:
    """把文本哈希成确定性向量：同一段文字得到同一个向量，便于验证检索。"""
    vec = np.zeros(dim, dtype=np.float32)
    for i, ch in enumerate(text):
        vec[(ord(ch) * 31 + i) % dim] += 1.0
    norm = float(np.linalg.norm(vec)) or 1.0
    return (vec / norm).tolist()


class _OllamaStub(BaseHTTPRequestHandler):
    models: list[str] = ["bge-m3:latest"]
    hits = {"tags": 0, "embed": 0, "embeddings": 0}

    def log_message(self, *args) -> None:  # 让 pytest 输出干净
        return

    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/tags":
            _OllamaStub.hits["tags"] += 1
            self._json({"models": [{"name": m, "model": m} for m in _OllamaStub.models]})
            return
        self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            payload = {}

        if self.path == "/api/embed":
            _OllamaStub.hits["embed"] += 1
            inputs = payload.get("input")
            if isinstance(inputs, str):
                inputs = [inputs]
            self._json({"embeddings": [_fake_vector(t) for t in (inputs or [])]})
            return

        if self.path == "/api/embeddings":
            _OllamaStub.hits["embeddings"] += 1
            self._json({"embedding": _fake_vector(str(payload.get("prompt") or ""))})
            return

        self._json({"error": "not found"}, 404)


@pytest.fixture
def ollama_stub():
    """起一个真的在监听端口的假 Ollama，返回 base_url。"""
    _OllamaStub.models = ["bge-m3:latest"]
    _OllamaStub.hits = {"tags": 0, "embed": 0, "embeddings": 0}
    server = ThreadingHTTPServer(("127.0.0.1", 0), _OllamaStub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def dead_port() -> str:
    """一个确定没人监听的端口（先占再释放，避免和真实服务撞车）。"""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return f"http://127.0.0.1:{port}"


@pytest.fixture
def use_ollama(monkeypatch, ollama_stub):
    """把配置切到 ollama 并指向假服务，然后强制重新探测。"""
    from app.config import settings
    from app.rag.embeddings import reset_embedder

    monkeypatch.setattr(settings, "embedding_provider", "ollama")
    monkeypatch.setattr(settings, "ollama_base_url", ollama_stub)
    monkeypatch.setattr(settings, "ollama_embedding_model", "bge-m3")
    reset_embedder()
    yield ollama_stub
    reset_embedder()


# ---------------- 1. 真的走 HTTP，维度来自服务返回 ----------------


def test_ollama_embedder_calls_real_http_and_uses_returned_dim(use_ollama):
    from app.rag.embeddings import get_embedder

    emb = get_embedder()
    assert emb.name == "ollama", "配置为 ollama 时必须真的选到 OllamaEmbedder"

    vectors = emb.embed(["同城配送几天能到？", "退款多久到账？"])
    assert _OllamaStub.hits["embed"] == 1, "必须真的发出了 /api/embed 请求"
    assert vectors.shape == (2, EMBED_DIM), f"维度应来自服务返回的 {EMBED_DIM}"
    assert emb.dim == EMBED_DIM
    # 不能是本地哈希的 4096
    assert vectors.shape[1] != 4096
    # 每行已 L2 归一化（点积即余弦）
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-5)


def test_embedding_status_separates_configured_and_active(use_ollama):
    from app.rag.embeddings import embedding_status

    status = embedding_status()
    assert status["configured_provider"] == "ollama"
    assert status["active_provider"] == "ollama"
    assert status["is_fallback"] is False
    assert status["model"] == "bge-m3"
    assert status["is_semantic"] is True
    assert status["model_installed"] is True
    assert status["available"] is True


# ---------------- 2. 服务通了但模型没 pull ----------------

def test_missing_model_is_reported_not_treated_as_ready(monkeypatch, ollama_stub):
    from app.config import settings
    from app.rag.embeddings import OllamaEmbedder

    _OllamaStub.models = ["llama3:latest"]  # 服务在跑，但没有 bge-m3
    emb = OllamaEmbedder(model="bge-m3", base_url=ollama_stub)
    health = emb.health()

    assert health["service_reachable"] is True
    assert health["model_installed"] is False
    # “服务能连上”不等于“能产出向量”，available 必须为 False
    assert health["available"] is False
    assert "bge-m3" in health["detail"]
    assert "llama3:latest" in health["installed_models"]

    # 配置为 ollama 时不能硬用，要降级并说明原因
    monkeypatch.setattr(settings, "embedding_provider", "ollama")
    monkeypatch.setattr(settings, "ollama_base_url", ollama_stub)
    from app.rag.embeddings import embedding_status, reset_embedder

    reset_embedder()
    status = embedding_status()
    assert status["active_provider"] == "local-hashing"
    assert status["is_fallback"] is True
    assert "bge-m3" in (status["fallback_reason"] or "")


# ---------------- 3. Ollama 不可用时知识库仍然可用 ----------------

def test_fallback_when_ollama_down_keeps_knowledge_base_usable(monkeypatch, dead_port, client):
    from app.config import settings
    from app.rag.embeddings import embedding_status, reset_embedder

    monkeypatch.setattr(settings, "embedding_provider", "ollama")
    monkeypatch.setattr(settings, "ollama_base_url", dead_port)
    reset_embedder()

    status = embedding_status()
    assert status["active_provider"] == "local-hashing"
    assert status["is_fallback"] is True
    assert "端口未监听" in (status["fallback_reason"] or "") or "无法连接" in (
        status["fallback_reason"] or ""
    )
    assert status["dim"] == settings.embedding_dim  # 本地哈希维度，不是 1024
    assert status["index_dim_note"]

    # 降级之后，上传 + 检索必须照常工作（不能因为连不上 Ollama 就让整库失效）
    up = client.post(
        "/api/knowledge/upload",
        files={"file": ("降级测试.md", "退货运费由谁承担，视责任方而定。".encode("utf-8"), "text/markdown")},
        params={"replace": "true"},
    )
    assert up.status_code == 201
    assert up.json()["status"] == "indexed"

    chat = client.post("/api/chat", json={"message": "退货运费谁承担"})
    assert chat.status_code == 200
    assert chat.json()["retrieval"]["has_context"] is True

    health = client.get("/api/health").json()
    assert health["embedding"]["active_provider"] == "local-hashing"
    assert health["embedding"]["fallback_reason"]
    assert any("降级" in w or "本地哈希" in w for w in health["warnings"])


# ---------------- 4. 重建索引失败不能毁掉旧索引 ----------------

def _upload(client, name: str, text: str) -> None:
    resp = client.post(
        "/api/knowledge/upload",
        files={"file": (name, text.encode("utf-8"), "text/markdown")},
        params={"replace": "true"},
    )
    assert resp.status_code == 201, resp.text


def test_reindex_failure_keeps_previous_index_intact(client, db, monkeypatch):
    """这是本次修复的核心回归：旧实现先 clear() 再重建，失败即清空。"""
    from app.rag import vector_store
    from app.services import knowledge_service

    _upload(client, "物流说明.md", "同城配送出库后 1 至 2 天送达。")
    _upload(client, "退款说明.md", "退款在仓库验收后 1 至 3 个工作日内发起。")

    index = vector_store.get_index()
    before_size = index.size
    before_sig = index.signature
    before_texts = sorted(r.text for r in index.documents())
    assert before_size >= 2

    class BrokenEmbedder:
        name = "broken"
        dim = 999
        is_semantic = True

        def embed(self, texts):
            raise RuntimeError("模拟 Ollama 中途掉线")

        def signature(self):
            return "broken:999"

        def health(self):
            return {"provider": self.name, "dim": self.dim}

    monkeypatch.setattr(knowledge_service, "get_embedder", lambda: BrokenEmbedder())

    with pytest.raises(knowledge_service.KnowledgeError) as excinfo:
        knowledge_service.reindex_all(db)
    assert "旧索引" in str(excinfo.value.message) and "保留" in str(excinfo.value.message)

    # 线上索引必须原封不动：数量、签名、片段内容都不变
    assert index.size == before_size
    assert index.signature == before_sig
    assert sorted(r.text for r in index.documents()) == before_texts

    # 重新加载一次（模拟进程重启）也要能读回来，而不是空索引
    fresh = vector_store.VectorIndex(index.dir)
    assert fresh.size == before_size
    assert fresh.signature == before_sig

    # 检索仍然正常
    chat = client.post("/api/chat", json={"message": "同城配送几天能到"})
    assert chat.json()["retrieval"]["has_context"] is True


def test_reindex_success_swaps_index_to_new_dimension(client, db, monkeypatch, ollama_stub):
    """从哈希(4096)切到 bge-m3(1024)：必须先 needs_reindex，重建后维度才对。"""
    from app.config import settings
    from app.rag import vector_store
    from app.rag.embeddings import get_embedder, reset_embedder
    from app.services import knowledge_service

    # 1) 先按 conftest 默认的本地哈希建索引（4096 维）
    _upload(client, "配送说明.md", "同城配送出库后 1 至 2 天送达，跨省 3 至 5 天。")
    index = vector_store.get_index()
    assert index.stats()["dim"] == 4096

    # 2) 再切到 Ollama（此时才允许 reset，顺序反了测的就不是“切换”了）
    monkeypatch.setattr(settings, "embedding_provider", "ollama")
    monkeypatch.setattr(settings, "ollama_base_url", ollama_stub)
    monkeypatch.setattr(settings, "ollama_embedding_model", "bge-m3")
    reset_embedder()

    health = client.get("/api/health").json()
    assert health["retrieval"]["needs_reindex"] is True, "换了 embedding 必须提示重建"

    result = knowledge_service.reindex_all(db)

    assert result["provider"] == "ollama"
    assert result["failed"] == 0
    assert result["dim"] == EMBED_DIM
    assert index.stats()["dim"] == EMBED_DIM
    assert index.signature == f"ollama:{get_embedder().model}"

    health_after = client.get("/api/health").json()
    assert health_after["retrieval"]["needs_reindex"] is False

    chat = client.post("/api/chat", json={"message": "同城配送几天能到"})
    data = chat.json()
    assert data["retrieval"]["has_context"] is True
    assert data["sources"][0]["file_name"] == "配送说明.md"

    # 无关问题必须拒答，不能因为换了模型就变得“什么都敢答”
    off = client.post("/api/chat", json={"message": "火星上的配送要几天"})
    assert off.json()["retrieval"]["has_context"] is False
    assert off.json()["sources"] == []


# ---------------- 5. 维度/签名不一致要拒绝写入，而不是混进索引 ----------------


def test_mismatched_dimension_is_rejected_before_mutating_index(client):
    from app.rag.vector_store import ChunkRecord, get_index

    _upload(client, "甲.md", "甲乙丙丁戊己庚辛。")
    index = get_index()
    before = index.size
    before_sig = index.signature

    wrong = np.zeros((1, 128), dtype=np.float32)
    wrong[0, 0] = 1.0
    with pytest.raises(ValueError):
        index.upsert_document(
            document_id="doc-x",
            file_name="x.md",
            texts=["随便一段"],
            vectors=wrong,
            signature="other:128",
        )

    # 抛异常前不能改动已有内容（旧实现会先删掉该文档的片段再报错）
    assert index.size == before
    assert index.signature == before_sig


