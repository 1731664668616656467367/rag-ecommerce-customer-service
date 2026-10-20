"""集中配置层。

所有环境变量、路径、限制参数都在这里读取一次，其他模块只 import settings，
不直接读 os.environ。这样换部署环境时只改 .env，不用改代码。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

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

    # ---------- DeepSeek 大模型 ----------
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
    knowledge_dir: str = str(PROJECT_DIR / "knowledge_base")
    upload_dir: str = str(BACKEND_DIR / "data" / "uploads")
    index_dir: str = str(BACKEND_DIR / "data" / "index")

    # ---------- 上传限制 ----------
    max_upload_mb: int = 10
    allowed_extensions: str = ".txt,.md,.pdf,.docx"

    # ---------- 会话 ----------
    max_message_chars: int = 2000
    history_window: int = 8

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


@lru_cache
def get_settings() -> Settings:
    """缓存单例，避免每次请求都重新解析 .env。"""
    return Settings()


settings = get_settings()
