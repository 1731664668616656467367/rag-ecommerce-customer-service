"""FastAPI 应用入口。

只做三件事：装配路由、配置中间件、启动时初始化（建表 + 导入样例知识库）。
业务逻辑一律不在这个文件里。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import (
    chat,
    feedback,
    health,
    knowledge,
    sessions,
    settings as settings_routes,
    stats,
)
from app.config import settings
from app.db.session import get_session_factory, init_db
from app.services.knowledge_service import seed_from_directory
from app.services.settings_service import load_answer_mode

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    logger.info("数据库已就绪：%s", settings.database_url)
    db = get_session_factory()()
    try:
        # 先把用户上次在页面上选的回答模式读回内存，
        # 否则重启后模式会悄悄回到 .env 的值，用户会以为设置没保存。
        load_answer_mode(db)
        result = seed_from_directory(db)
        if result.get("imported"):
            logger.info("已导入样例知识库：%s", result["imported"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("启动初始化失败（不影响启动）：%s", exc)
    finally:
        db.close()
    yield


app = FastAPI(
    title=settings.app_name,
    version=health.VERSION,
    description="电商智能客服 RAG 后端：意图识别 + 知识库检索 + DeepSeek 生成",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api"
app.include_router(health.router, prefix=API_PREFIX)
app.include_router(stats.router, prefix=API_PREFIX)
app.include_router(chat.router, prefix=API_PREFIX)
app.include_router(settings_routes.router, prefix=API_PREFIX)
app.include_router(sessions.router, prefix=API_PREFIX)
app.include_router(knowledge.router, prefix=API_PREFIX)
app.include_router(feedback.router, prefix=API_PREFIX)


@app.exception_handler(RequestValidationError)
async def validation_handler(_req: Request, exc: RequestValidationError) -> JSONResponse:
    """把 Pydantic 的报错整理成人类可读的一句话，同时保留细节。

    注意：exc.errors() 里的 ctx 可能包含 ValueError 实例，直接塞进 JSONResponse
    会序列化失败（TypeError）。所以这里只挑能安全序列化的字段。
    """
    raw_errors = exc.errors()
    details = [
        {
            "loc": [str(x) for x in e.get("loc", [])],
            "msg": str(e.get("msg", "")),
            "type": str(e.get("type", "")),
        }
        for e in raw_errors
    ]
    first = details[0] if details else {}
    field = ".".join(first.get("loc", [])[1:]) or "请求体"
    reason = first.get("msg", "参数不合法")
    return JSONResponse(
        status_code=422,
        content={"detail": f"{field}: {reason}", "code": "validation_error", "errors": details},
    )


@app.exception_handler(StarletteHTTPException)
async def http_handler(_req: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": f"http_{exc.status_code}"},
    )


@app.exception_handler(Exception)
async def unhandled_handler(_req: Request, exc: Exception) -> JSONResponse:
    # 只记异常类型和消息，不记完整对话内容，避免敏感信息落日志
    logger.exception("未处理异常：%s", type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误", "code": "internal_error"},
    )


# ---------------------------------------------------------------------------
# 前后端单端口合并：挂载前端静态产物。
# 优先 backend/static（部署时预置的 next build 产物），其次 frontend/out（本地开发）。
# 只有存在 index.html 才挂载，纯后端开发（无产物）不受影响。
# ---------------------------------------------------------------------------
def _pick_static_dir() -> Path | None:
    for candidate in (Path(settings.static_dir), Path(settings.frontend_out_dir)):
        if candidate.exists() and (candidate / "index.html").exists():
            return candidate
    return None


_STATIC_DIR = _pick_static_dir()
if _STATIC_DIR is not None:
    _PAGES = ("chat", "knowledge", "settings")

    @app.get("/", include_in_schema=False)
    async def index_page() -> FileResponse:
        return FileResponse(str(_STATIC_DIR / "index.html"))

    @app.get("/{page}", include_in_schema=False)
    async def spa_page(page: str):
        # 已知前端页面路径 → 返回对应静态 HTML（SPA 路由回退）。
        if page in _PAGES:
            candidate = _STATIC_DIR / page / "index.html"
            if candidate.exists():
                return FileResponse(str(candidate))
        return JSONResponse(status_code=404, content={"detail": "页面不存在", "code": "http_404"})

    # 静态资源（_next/*、icon.svg 等）挂到根；API 路由已在前注册，优先命中。
    # redirect_slashes=False 关闭 /chat -> /chat/ 的 307，避免前端页面被重定向。
    app.mount(
        "/",
        StaticFiles(directory=str(_STATIC_DIR), html=True),
        name="frontend",
    )
    # StaticFiles 默认会对 /chat -> /chat/ 做 307，这里关掉它。
    _static_app = app.routes[-1]
    _static_app.app.redirect_slashes = False

    logger.info("已挂载前端静态目录：%s", _STATIC_DIR)
else:
    @app.get("/", include_in_schema=False)
    def root() -> dict:
        return {"name": settings.app_name, "docs": "/docs", "health": "/api/health"}
