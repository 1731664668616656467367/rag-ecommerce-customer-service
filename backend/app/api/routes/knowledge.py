"""知识库管理接口。

安全说明：当前没有登录体系，因此这些接口在开发环境是开放的。
生产部署前必须加认证，否则任何人都能上传/删除知识库。
这一点在 /api/health 与 README 中都会明确标注，不假装已经安全。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy.orm import Session as OrmSession

from app.db.session import get_db
from app.rag.vector_store import get_index
from app.schemas.models import DocumentOut, KnowledgeListResponse
from app.services import knowledge_service

router = APIRouter(tags=["knowledge"])


@router.get("/knowledge", response_model=KnowledgeListResponse)
def list_knowledge(db: OrmSession = Depends(get_db)):
    docs = knowledge_service.list_documents(db)
    return KnowledgeListResponse(
        documents=[DocumentOut.model_validate(d) for d in docs],
        index=get_index().stats(),
    )


@router.post("/knowledge/upload", response_model=DocumentOut, status_code=201)
async def upload_knowledge(
    file: UploadFile = File(...),
    replace: bool = Query(default=True, description="同名文件是否覆盖"),
    db: OrmSession = Depends(get_db),
):
    if file.filename is None:
        raise HTTPException(status_code=400, detail="缺少文件名")
    content = await file.read()
    try:
        doc = knowledge_service.add_document(db, file.filename, content, replace=replace)
    except knowledge_service.KnowledgeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return DocumentOut.model_validate(doc)


@router.delete("/knowledge/{document_id}", status_code=204, response_class=Response)
def delete_knowledge(document_id: str, db: OrmSession = Depends(get_db)) -> Response:
    try:
        knowledge_service.delete_document(db, document_id)
    except knowledge_service.KnowledgeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return Response(status_code=204)


@router.post("/knowledge/reindex")
def reindex(db: OrmSession = Depends(get_db)) -> dict:
    return knowledge_service.reindex_all(db)
