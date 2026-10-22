"""知识库文档服务：上传、索引、列表、删除。

文件与索引的一致性是这个模块的核心难点：
- 上传失败 -> 数据库状态置 failed，并写明原因，不留半成品索引。
- 重新上传同名文件 -> 覆盖旧文档，旧向量先删再写（不是追加）。
- 删除文档 -> 先删向量，再删磁盘文件，最后删数据库记录；任何一步失败都要有明确状态。
- 文件名不直接当路径用，统一生成 UUID 存储名，防止 ../../ 路径穿越。
"""

from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.config import settings
from app.db.models import KnowledgeDocument
from app.rag.chunker import chunk_text, clean_text
from app.rag.embeddings import get_embedder
from app.rag.loaders import SUPPORTED, DocumentError, load_document
from app.rag.vector_store import VectorIndex, get_index

logger = logging.getLogger(__name__)


class KnowledgeError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class DuplicateError(KnowledgeError):
    def __init__(self, message: str = "同名文档已存在") -> None:
        super().__init__(message, 409)


def _safe_suffix(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED or suffix not in settings.allowed_extension_set:
        allowed = "、".join(sorted(settings.allowed_extension_set))
        raise KnowledgeError(f"不支持的文件类型 {suffix or '(无扩展名)'}，仅支持：{allowed}")
    return suffix


def _validate_name(filename: str) -> str:
    name = Path(filename or "").name.strip()
    if not name or name in (".", ".."):
        raise KnowledgeError("文件名无效")
    if len(name) > 200:
        raise KnowledgeError("文件名过长")
    return name


def list_documents(db: OrmSession) -> list[KnowledgeDocument]:
    stmt = select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc())
    return list(db.scalars(stmt))


def get_document(db: OrmSession, document_id: str) -> KnowledgeDocument:
    doc = db.get(KnowledgeDocument, document_id)
    if doc is None:
        raise KnowledgeError("文档不存在", 404)
    return doc


def _index_texts(doc: KnowledgeDocument, text: str) -> int:
    """切块 + 向量化 + 写入索引。返回片段数。"""
    chunks = chunk_text(text)
    if not chunks:
        raise KnowledgeError("文档没有可索引的有效内容", 422)
    embedder = get_embedder()
    vectors = embedder.embed(chunks)
    index = get_index()
    return index.upsert_document(
        document_id=doc.id,
        file_name=doc.file_name,
        texts=chunks,
        vectors=vectors,
        index_version=doc.index_version,
        signature=embedder.signature(),
    )


def add_document(
    db: OrmSession,
    filename: str,
    content: bytes,
    replace: bool = True,
) -> KnowledgeDocument:
    name = _validate_name(filename)
    suffix = _safe_suffix(name)

    if not content:
        raise KnowledgeError("文件内容为空", 422)
    if len(content) > settings.max_upload_bytes:
        raise KnowledgeError(f"文件超过 {settings.max_upload_mb}MB 限制", 413)

    # 简单的内容嗅探：纯二进制且不是 pdf/docx，直接拒绝
    if suffix in (".txt", ".md", ".markdown") and b"\x00" in content[:2048]:
        raise KnowledgeError("文件看起来不是纯文本，请检查后重新上传", 422)

    existing = db.scalar(
        select(KnowledgeDocument).where(KnowledgeDocument.file_name == name)
    )
    if existing is not None:
        if not replace:
            raise DuplicateError()
        logger.info("覆盖同名文档：%s", name)
        delete_document(db, existing.id, missing_ok=True)

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    stored_path = upload_dir / stored_name
    stored_path.write_bytes(content)

    doc = KnowledgeDocument(
        file_name=name,
        stored_name=stored_name,
        file_type=suffix.lstrip("."),
        size_bytes=len(content),
        status="pending",
        index_version="v1",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    try:
        text = load_document(stored_path)
        text = clean_text(text)
        count = _index_texts(doc, text)
        doc.chunk_count = count
        doc.status = "indexed"
        doc.error = None
        db.commit()
        db.refresh(doc)
        logger.info("文档已索引：%s（%d 个片段）", name, count)
        return doc
    except (DocumentError, KnowledgeError) as exc:
        message = getattr(exc, "message", str(exc))
        doc.status = "failed"
        doc.error = message
        db.commit()
        get_index().remove_document(doc.id)
        # 刻意保留原始文件与失败记录：
        # 用户在知识库页面能看到“处理失败 + 原因”，也便于排查是否是文件本身的问题。
        # 索引里不会留残片，所以不会污染检索。
        raise KnowledgeError(message, getattr(exc, "status_code", 422)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("索引失败")
        doc.status = "failed"
        doc.error = f"索引失败：{type(exc).__name__}"
        db.commit()
        get_index().remove_document(doc.id)
        raise KnowledgeError("文档索引失败，请检查文件内容或 embedding 配置", 500) from exc


def delete_document(db: OrmSession, document_id: str, missing_ok: bool = False) -> None:
    doc = db.get(KnowledgeDocument, document_id)
    if doc is None:
        if missing_ok:
            return
        raise KnowledgeError("文档不存在", 404)

    # 先摘索引：只删本文档的片段，其它文档不受影响
    removed = get_index().remove_document(doc.id)
    file_path = Path(settings.upload_dir) / doc.stored_name
    try:
        file_path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("删除磁盘文件失败：%s", exc)

    db.delete(doc)
    db.commit()
    logger.info("文档已删除：%s（清理 %d 个片段）", doc.file_name, removed)


def reindex_all(db: OrmSession) -> dict:
    """全量重建：先在**暂存区**建好，全部成功才替换线上索引。

    为什么不能沿用“先 clear() 再逐篇重建”：
        clear() 会立刻把空索引写盘。之后只要有一篇失败（Ollama 掉线、
        换了模型维度对不上、磁盘满），旧向量已经没了，
        知识库当场变成“不可检索”——一次失败的维护动作把线上服务打挂。
        所以这里改成：
          1. 在 data/index_staging_xxx 里建一份新索引（不碰线上文件）；
          2. 有任何一篇成功 → 用这份新索引整体替换线上索引；
          3. 全部失败 → 删掉暂存目录并报错，线上索引一个字节都不动。
    """
    docs = list_documents(db)
    if not docs:
        raise KnowledgeError("知识库里还没有文档，无需重建", 409)

    embedder = get_embedder()
    signature = embedder.signature()
    staging_dir = Path(settings.index_dir).parent / f"index_staging_{uuid.uuid4().hex[:8]}"
    staging = VectorIndex(staging_dir)  # 空目录：不会读到线上数据

    ok, failed = 0, 0
    errors: list[dict] = []
    succeeded: list[tuple[str, int]] = []
    try:
        for doc in docs:
            doc_id, doc_name, index_version = doc.id, doc.file_name, doc.index_version
            path = Path(settings.upload_dir) / doc.stored_name
            try:
                if not path.exists():
                    raise KnowledgeError("原始文件缺失，无法重建该文档", 422)
                text = clean_text(load_document(path))
                chunks = chunk_text(text)
                if not chunks:
                    raise KnowledgeError("文档没有可索引的有效内容", 422)
                vectors = embedder.embed(chunks)
                staging.upsert_document(
                    document_id=doc_id,
                    file_name=doc_name,
                    texts=chunks,
                    vectors=vectors,
                    index_version=index_version,
                    signature=signature,
                )
            except Exception as exc:  # noqa: BLE001
                db.rollback()  # 不让上一篇的半截事务带进下一篇
                failed += 1
                errors.append({"file_name": doc_name, "error": str(exc)[:200]})
                continue
            succeeded.append((doc_id, len(chunks)))
            ok += 1

        # 一篇都没成就直接失败返回：此时**数据库和索引都不动**。
        # 如果这里顺手把文档标成 failed，页面会显示“5 份全部处理失败”，
        # 而实际检索仍然可用 —— 状态与事实不符，比不更新更糟。
        if ok == 0:
            first = errors[0]["error"] if errors else "未知原因"
            raise KnowledgeError(
                f"重建失败：{failed} 份文档全部失败，线上旧索引与文档状态均已保留。首个错误：{first}",
                503,
            )

        records, vectors = staging.snapshot()
        live = get_index()
        # 唯一会改动线上索引的一步：数量与维度都在 replace_all 里校验过
        live.replace_all(records, vectors, signature)

        # 索引替换成功之后才落库状态，避免“索引没换成、文档却标了 failed/indexed”
        for doc_id, chunk_count in succeeded:
            row = db.get(KnowledgeDocument, doc_id)
            if row is not None:
                row.chunk_count = chunk_count
                row.status = "indexed"
                row.error = None
        for item in errors:
            row = db.scalar(
                select(KnowledgeDocument).where(KnowledgeDocument.file_name == item["file_name"])
            )
            if row is not None:
                row.status = "failed"
                row.error = item["error"]
        db.commit()
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)

    return {
        "indexed": ok,
        "failed": failed,
        "chunks": live.size,
        "dim": int(vectors.shape[1]) if vectors.size else 0,
        "provider": embedder.name,
        "signature": signature,
        "errors": errors[:5],
    }


def seed_from_directory(db: OrmSession, directory: str | None = None) -> dict:
    """启动时把 knowledge_base/ 里的样例文档导入（仅当数据库为空）。"""
    if list_documents(db):
        return {"skipped": True, "reason": "已有文档，跳过种子导入"}

    base = Path(directory or settings.knowledge_dir)
    if not base.exists():
        return {"skipped": True, "reason": "样例目录不存在"}

    imported, failed = [], []
    for path in sorted(base.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in settings.allowed_extension_set:
            continue
        try:
            add_document(db, path.name, path.read_bytes())
            imported.append(path.name)
        except KnowledgeError as exc:
            failed.append({"file": path.name, "error": exc.message})
    return {"imported": imported, "failed": failed}
