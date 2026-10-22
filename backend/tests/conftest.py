"""测试基座。

必须在 import app 之前设置环境变量，因为 settings 在模块加载时就被读取并缓存。
测试使用独立的临时目录，绝不碰开发用的 data/app.db 和 data/index。
"""

from __future__ import annotations

import os
import shutil
import socket
import tempfile
from pathlib import Path

import httpx
import pytest

TMP_ROOT = Path(tempfile.mkdtemp(prefix="ecom_test_"))

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = f"sqlite:///{(TMP_ROOT / 'test.db').as_posix()}"
os.environ["UPLOAD_DIR"] = str(TMP_ROOT / "uploads")
os.environ["INDEX_DIR"] = str(TMP_ROOT / "index")
os.environ["KNOWLEDGE_DIR"] = str(TMP_ROOT / "empty_kb")
os.environ["EMBEDDING_PROVIDER"] = "local"
# 默认就用纯知识库模式，测试跑的就是生产默认行为
os.environ["ANSWER_MODE"] = "knowledge_only"
os.environ["RETRIEVAL_MODE"] = "hybrid"
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
    from app.llm import status as llm_status
    from app.runtime_mode import reset_override

    # 运行期模式与模型状态是进程级全局，必须在每个用例前复位，
    # 否则上一个用例切换过的模式会污染下一个用例（表现为随机失败）。
    reset_override()
    llm_status.reset()

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
def llm_mode(monkeypatch):
    """显式切换到 llm 模式。用于测试模型生成与降级路径。"""
    from app.config import settings

    monkeypatch.setattr(settings, "answer_mode", "llm")
    return settings


@pytest.fixture
def no_network(monkeypatch):
    """任何出网尝试都会抛错并记录，用于证明零外联。

    放在 conftest 而不是某个测试文件里：对话引导、纯知识库两条链路都要用它，
    各写一份的话，某天只改了一处就会留下一个假的“通过”。
    """
    attempts: list[str] = []

    def deny_socket(*args, **kwargs):
        attempts.append(f"socket:{args[:1]}")
        # 抛 httpx 的连接错误：让被测代码走正常的“模型不可用”分支，
        # 而不是让测试因为未捕获异常而挂掉（这样才能断言降级行为）
        raise httpx.ConnectError("blocked by test: no network allowed")

    # 拦在“传输层”，而不是 httpx.Client.send：
    # 测试客户端（ASGITransport）也走 send，拦错层会把测试自己打死。
    async def deny_async_transport(self, request):
        attempts.append(f"httpx-async:{request.url}")
        raise httpx.ConnectError("blocked by test: no network allowed")

    def deny_transport(self, request):
        attempts.append(f"httpx-sync:{request.url}")
        raise httpx.ConnectError("blocked by test: no network allowed")

    # 只拦“真正建立 TCP 连接”的入口。
    # 不能 patch socket.socket.connect：Windows 上 TestClient 的事件循环自建管道也走它，
    # 会把测试框架自己拦死（这条教训保留在注释里）。
    monkeypatch.setattr(socket, "create_connection", deny_socket)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", deny_transport)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", deny_async_transport)
    return attempts


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
