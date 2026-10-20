"""知识库接口测试：上传、列表、删除、失败场景、路径安全。"""

from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.rag.vector_store import get_index


def _upload(client, name: str, content: bytes, replace: bool = True):
    return client.post(
        "/api/knowledge/upload",
        files={"file": (name, content, "text/markdown")},
        params={"replace": str(replace).lower()},
    )


def test_upload_txt_indexes_document(client):
    resp = _upload(client, "退款说明.md", "退款在仓库验收后 1 至 3 个工作日内发起。".encode("utf-8"))
    assert resp.status_code == 201
    doc = resp.json()
    assert doc["status"] == "indexed"
    assert doc["chunk_count"] >= 1
    assert get_index().size >= 1

    listing = client.get("/api/knowledge").json()
    assert listing["documents"][0]["file_name"] == "退款说明.md"
    assert listing["index"]["chunks"] >= 1


def test_upload_then_retrieval_works(client):
    _upload(client, "物流说明.md", "同城配送出库后 1 至 2 天送达，跨省 3 至 5 天。".encode("utf-8"))
    resp = client.post("/api/chat", json={"message": "同城配送几天能到"})
    data = resp.json()
    assert data["retrieval"]["has_context"] is True
    assert data["sources"][0]["file_name"] == "物流说明.md"


def test_upload_rejects_unsupported_type(client):
    resp = _upload(client, "恶意.exe", b"MZ\x90\x00binary")
    assert resp.status_code == 400
    assert "不支持的文件类型" in resp.json()["detail"]


def test_upload_rejects_empty_file(client):
    resp = _upload(client, "空.md", b"")
    assert resp.status_code == 422


def test_upload_rejects_oversize(client, monkeypatch):
    monkeypatch.setattr(type(settings), "max_upload_bytes", property(lambda self: 1024))
    resp = _upload(client, "大文件.md", b"a" * 4096)
    assert resp.status_code == 413
    assert "限制" in resp.json()["detail"]


def test_upload_rejects_binary_disguised_as_text(client):
    resp = _upload(client, "假的.md", b"normal text\x00\x00hidden")
    assert resp.status_code == 422


def test_upload_without_replace_returns_409(client):
    _upload(client, "重复.md", "第一版内容说明".encode("utf-8"))
    resp = _upload(client, "重复.md", "第二版内容说明".encode("utf-8"), replace=False)
    assert resp.status_code == 409


def test_delete_document_updates_index(client):
    first = _upload(client, "A.md", "退款三个工作日到账。".encode("utf-8")).json()
    _upload(client, "B.md", "物流同城次日达。".encode("utf-8"))
    before = get_index().size

    assert client.delete(f"/api/knowledge/{first['id']}").status_code == 204
    assert get_index().size < before
    names = [d["file_name"] for d in client.get("/api/knowledge").json()["documents"]]
    assert "A.md" not in names
    assert "B.md" in names


def test_delete_unknown_document_404(client):
    assert client.delete("/api/knowledge/nope").status_code == 404


def test_upload_filename_path_traversal_is_sanitized(client):
    """文件名里的 ../ 不能影响真实存储路径。"""
    resp = _upload(client, "../../evil.md", "试图穿越目录的内容".encode("utf-8"))
    assert resp.status_code == 201
    doc = resp.json()
    assert doc["file_name"] == "evil.md"

    upload_dir = Path(settings.upload_dir).resolve()
    stored = [p for p in upload_dir.iterdir() if p.is_file()]
    assert stored, "文件应存在于上传目录"
    for p in stored:
        assert p.resolve().parent == upload_dir
    assert not (upload_dir.parent.parent / "evil.md").exists()


def test_failed_parse_marks_status(client, monkeypatch):
    """模拟解析失败：不应留下索引，也不应留下半成品文件。"""
    from app.rag import loaders

    def boom(_path):
        raise loaders.DocumentError("模拟解析失败")

    monkeypatch.setattr("app.services.knowledge_service.load_document", boom)
    resp = _upload(client, "坏文件.md", "内容".encode("utf-8"))
    assert resp.status_code == 422
    # 索引必须是干净的
    assert get_index().size == 0
    # 但失败记录要保留，用户才能在页面上看到“处理失败 + 原因”
    docs = client.get("/api/knowledge").json()["documents"]
    assert len(docs) == 1
    assert docs[0]["status"] == "failed"
    assert "模拟解析失败" in docs[0]["error"]
    assert len(list(Path(settings.upload_dir).iterdir())) == 1
