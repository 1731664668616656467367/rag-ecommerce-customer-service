"""DeepSeek 客户端（OpenAI 兼容协议）。

只在这里使用 API Key。前端永远拿不到它：
前端 -> FastAPI -> 本模块 -> DeepSeek。
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.llm.base import (
    LLMAuthError,
    LLMClient,
    LLMNotConfigured,
    LLMQuotaExceeded,
    LLMTimeout,
    LLMUnavailable,
)

logger = logging.getLogger(__name__)


class DeepSeekClient(LLMClient):
    name = "deepseek"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.api_key = (api_key if api_key is not None else settings.deepseek_api_key).strip()
        self.base_url = (base_url or settings.deepseek_base_url).rstrip("/")
        self.model = model or settings.deepseek_model
        self.timeout = timeout or settings.llm_timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def complete(self, messages: list[dict], temperature: float = 0.3) -> str:
        if not self.configured:
            raise LLMNotConfigured()

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_exc: Exception | None = None
        attempts = max(1, settings.llm_max_retries + 1)
        for attempt in range(1, attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(
                        f"{self.base_url}/chat/completions", json=payload, headers=headers
                    )
                if resp.status_code in (401, 403):
                    # 不打印 key，只打印状态码
                    logger.error("DeepSeek 鉴权失败：HTTP %s", resp.status_code)
                    raise LLMAuthError()
                if resp.status_code == 402:
                    logger.error("DeepSeek 账户余额不足：HTTP 402")
                    raise LLMQuotaExceeded()
                if resp.status_code == 429:
                    logger.warning("DeepSeek 限流：HTTP 429")
                    raise LLMUnavailable("模型服务限流")
                if resp.status_code >= 500:
                    raise LLMUnavailable(f"上游错误 {resp.status_code}")
                if resp.status_code >= 400:
                    logger.error("DeepSeek 请求被拒：HTTP %s", resp.status_code)
                    raise LLMUnavailable(f"请求被拒绝 {resp.status_code}")

                data = resp.json()
                content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
                if not content or not content.strip():
                    raise LLMUnavailable("模型返回空内容")
                return content.strip()

            except httpx.TimeoutException as exc:
                last_exc = exc
                logger.warning("DeepSeek 超时（第 %d/%d 次）", attempt, attempts)
            except httpx.HTTPError as exc:
                last_exc = exc
                logger.warning("DeepSeek 网络错误（第 %d/%d 次）：%s", attempt, attempts, type(exc).__name__)

        if isinstance(last_exc, httpx.TimeoutException):
            raise LLMTimeout() from last_exc
        raise LLMUnavailable() from last_exc
