"""安全相关测试：密钥不泄露、错误不暴露内部细节、输入长度受限。"""

from __future__ import annotations

import re
from pathlib import Path

from app.config import PROJECT_DIR, settings

SECRET_PATTERN = re.compile(r"sk-[A-Za-z0-9]{16,}")
SCAN_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".json", ".yml", ".yaml", ".example"}
SKIP_DIRS = {".git", "node_modules", ".next", ".venv", "__pycache__", "data"}


def _iter_files():
    for path in PROJECT_DIR.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix in SCAN_SUFFIXES or path.name.startswith(".env"):
            yield path


def test_no_hardcoded_api_key_in_repository():
    offenders = []
    for path in _iter_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if SECRET_PATTERN.search(text):
            offenders.append(str(path.relative_to(PROJECT_DIR)))
    assert offenders == [], f"发现疑似硬编码密钥：{offenders}"


def test_health_does_not_expose_api_key(client):
    body = client.get("/api/health").text
    # 允许提示“未配置 DEEPSEEK_API_KEY”这个变量名，但绝不能出现真实值
    assert not SECRET_PATTERN.search(body)
    if settings.deepseek_api_key:
        assert settings.deepseek_api_key not in body


def test_env_example_uses_placeholder():
    example = Path(PROJECT_DIR) / "backend" / ".env.example"
    if not example.exists():
        return
    text = example.read_text(encoding="utf-8")
    assert "DEEPSEEK_API_KEY=" in text
    # 占位符必须明显是假的
    for line in text.splitlines():
        if line.startswith("DEEPSEEK_API_KEY="):
            value = line.split("=", 1)[1].strip()
            assert value in ("", "sk-your-key-here", "your-deepseek-api-key"), line


def test_unhandled_exception_returns_generic_message(monkeypatch):
    from fastapi.testclient import TestClient

    from app.api.routes import chat as chat_route
    from app.main import app

    async def boom(*_a, **_kw):
        raise RuntimeError("内部数据库密码是 xxx")

    monkeypatch.setattr(chat_route.chat_service, "handle_chat", boom)
    # raise_server_exceptions=False：让 500 处理器真的把响应写出来
    local = TestClient(app, raise_server_exceptions=False)
    resp = local.post("/api/chat", json={"message": "退款"})
    assert resp.status_code == 500
    body = resp.text
    assert "密码" not in body
    assert resp.json()["detail"] == "服务器内部错误"


def test_message_length_limit_enforced(client):
    resp = client.post("/api/chat", json={"message": "x" * 2001})
    assert resp.status_code == 422
