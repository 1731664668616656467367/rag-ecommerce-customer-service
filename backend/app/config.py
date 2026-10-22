"""集中配置层。

所有环境变量、路径、限制参数都在这里读取一次，其他模块只 import settings，
不直接读 os.environ。这样换部署环境时只改 .env，不用改代码。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---------- 应用 ----------
    app_name: str = "电商智能客服 RAG"
    app_env: str = "development"
    debug: bool = True
    log_level: str = "INFO"

    # 前端地址，用于 CORS。开发时 Next.js 默认 3000 端口。
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # ---------- 数据库 ----------
    # SQLite 文件放在 backend/data 下，方便和向量索引分开管理
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'data' / 'app.db').as_posix()}"

    # ---------- 运行模式（回答来源）----------
    # knowledge_only：只用本地规则 + 知识库检索回答，绝不发起任何外部模型请求
    # llm：显式开启大模型生成（必须手动改成这个值，不会因为存在 API Key 就自动启用）
    answer_mode: Literal["knowledge_only", "llm"] = "knowledge_only"

    # ---------- DeepSeek 大模型 ----------
    # 注意：即使这里填了 key，只要 answer_mode=knowledge_only，就不会有任何请求发出
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    llm_timeout_seconds: float = 30.0
    llm_max_retries: int = 1

    # ---------- Embedding ----------
    # 可选值: auto | ollama | local
    # auto: 先探测 Ollama，连不上就用本地离线词袋向量（保证系统可用）
    embedding_provider: str = "auto"
    ollama_base_url: str = "http://localhost:11434"
    ollama_embedding_model: str = "bge-m3"
    ollama_timeout_seconds: float = 15.0
    embedding_dim: int = 4096

    # ---------- RAG ----------
    chunk_size: int = 320
    chunk_overlap: int = 60
    retrieval_top_k: int = 4
    # 0 表示按 embedding 模型自动选择阈值（推荐）。
    # 想要固定值可以在这里写，例如 0.35；但换模型后需要重新校准。
    retrieval_min_score: float = 0.0
    # 检索通道：hybrid（向量 + BM25 融合，默认）| vector（仅向量）| lexical（仅 BM25）
    retrieval_mode: Literal["hybrid", "vector", "lexical"] = "hybrid"
    # 词法通道的最低加权覆盖度（见 rag/lexical.py 的 CorpusStats）。
    # 调高 = 更保守（宁可说“没找到”也不搬错段落）；调低 = 召回更多但误答风险上升。
    # 默认值按当前知识库实测校准，换语料后请重跑 scripts/eval_retrieval.py。
    retrieval_min_coverage: float = 0.12
    # 纯知识库模式回答时最多引用几个片段、每段截取多少字
    knowledge_answer_max_chunks: int = 3
    knowledge_answer_snippet_chars: int = 300
    # 样例知识库目录。优先 backend/knowledge_base（部署时自包含），
    # 其次项目根 knowledge_base（本地开发时的传统位置）。
    knowledge_dir: str = str(BACKEND_DIR / "knowledge_base")
    knowledge_dir_fallback: str = str(PROJECT_DIR / "knowledge_base")
    upload_dir: str = str(BACKEND_DIR / "data" / "uploads")
    index_dir: str = str(BACKEND_DIR / "data" / "index")
    # 前端静态产物目录。部署单端口时把 next build 的产物放到 backend/static/，
    # 后端会在启动时挂载它实现前后端合并；纯后端开发时该目录不存在，自动跳过。
    # 优先级：backend/static（部署）> frontend/out（本地 next build 默认输出）。
    static_dir: str = str(BACKEND_DIR / "static")
    frontend_out_dir: str = str(PROJECT_DIR / "frontend" / "out")

    # ---------- 上传限制 ----------
    max_upload_mb: int = 10
    allowed_extensions: str = ".txt,.md,.pdf,.docx"

    # ---------- 会话 ----------
    max_message_chars: int = 2000
    history_window: int = 8

    @field_validator("answer_mode", "retrieval_mode", mode="before")
    @classmethod
    def _normalize_mode(cls, v):
        """允许 .env 里写大小写混用或带空格，统一成小写。"""
        return str(v).strip().lower() if isinstance(v, str) else v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_extension_set(self) -> set[str]:
        return {e.strip().lower() for e in self.allowed_extensions.split(",") if e.strip()}

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def llm_configured(self) -> bool:
        """只有真的拿到 key 才算已配置，绝不编造一个假 key。"""
        return bool(self.deepseek_api_key.strip())

    @property
    def llm_enabled(self) -> bool:
        """是否允许调用大模型。只看显式配置，不看 key 是否存在。"""
        return self.answer_mode == "llm"

    @property
    def llm_ready(self) -> bool:
        """显式开启且配好了 key，才可能真正发出请求。"""
        return self.llm_enabled and self.llm_configured


@lru_cache
def get_settings() -> Settings:
    """缓存单例，避免每次请求都重新解析 .env。"""
    return Settings()


settings = get_settings()
