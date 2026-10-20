"""测试基座。

必须在 import app 之前设置环境变量，因为 settings 在模块加载时就被读取并缓存。
测试使用独立的临时目录，绝不碰开发用的 data/app.db 和 data/index。
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

TMP_ROOT = Path(tempfile.mkdtemp(prefix="ecom_test_"))

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = f"sqlite:///{(TMP_ROOT / 'test.db').as_posix()}"
os.environ["UPLOAD_DIR"] = str(TMP_ROOT / "uploads")
os.environ["INDEX_DIR"] = str(TMP_ROOT / "index")
os.environ["KNOWLEDGE_DIR"] = str(TMP_ROOT / "empty_kb")
os.environ["EMBEDDING_PROVIDER"] = "local"
os.environ["DEEPSEEK_API_KEY"] = ""
os.environ["RETRIEVAL_MIN_SCORE"] = "0.15"

from fastapi.testclient import TestClient  # noqa: E402

from app.db.models import Base, Feedback, KnowledgeDocument, Message, Session  # noqa: E402
from app.db.session import get_engine, get_session_factory, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.rag.embeddings import reset_embedder  # noqa: E402
from app.rag.vector_store import get_index, reset_index  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _database() -> None:
    init_db()


@pytest.fixture(autouse=True)
def clean_state():
    """每个测试前清空所有表与向量索引，保证测试互不影响。"""
    engine = get_engine()
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())

    upload_dir = Path(os.environ["UPLOAD_DIR"])
    if upload_dir.exists():
        shutil.rmtree(upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    index_dir = Path(os.environ["INDEX_DIR"])
    if index_dir.exists():
        shutil.rmtree(index_dir)
    index_dir.mkdir(parents=True, exist_ok=True)

    reset_index()
    reset_embedder()
    get_index().clear()
    yield


@pytest.fixture
def db():
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    # 不进入 with 上下文：跳过 lifespan 的样例知识库导入，保证测试数据可控
    return TestClient(app)


@pytest.fixture
def sample_text() -> str:
    return (
        "# 退换货政策\n\n"
        "自签收之日起 7 个自然日内，商品未使用且不影响二次销售的，可申请无理由退货。\n\n"
        "商品存在质量问题的，自签收之日起 15 日内可申请退货，30 日内可申请换货，需提供故障照片。\n\n"
        "退货商品经仓库验收合格后，退款将在 1 至 3 个工作日内发起，银行卡到账一般需要 1 至 7 个工作日。\n"
    )


@pytest.fixture
def indexed_doc(db, sample_text):
    from app.services import knowledge_service

    return knowledge_service.add_document(db, "退换货政策.md", sample_text.encode("utf-8"))
