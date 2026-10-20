"""测试替身：可控的假大模型。

为什么要 mock？
    真实调用 DeepSeek 每次都要花钱、有网络抖动、结果还不可重复。
    用假客户端可以精确模拟“超时”“返回非法意图”“返回空内容”这些边界情况，
    这是生产级测试的常规做法，不是偷懒。
"""

from __future__ import annotations

from app.llm.base import LLMClient, LLMQuotaExceeded, LLMTimeout, LLMUnavailable


class FakeLLM(LLMClient):
    name = "fake"
    model = "fake-model"

    def __init__(
        self,
        reply: str = "这是来自知识库的回答。",
        intent_reply: str | None = None,
        raise_error: Exception | None = None,
        configured: bool = True,
    ) -> None:
        self.reply = reply
        self.intent_reply = intent_reply
        self.raise_error = raise_error
        self.configured = configured
        self.calls: list[list[dict]] = []

    async def complete(self, messages: list[dict], temperature: float = 0.3) -> str:
        self.calls.append(messages)
        if self.raise_error is not None:
            raise self.raise_error
        if self.intent_reply is not None and "意图分类器" in (messages[0].get("content") or ""):
            return self.intent_reply
        return self.reply


class TimeoutLLM(FakeLLM):
    def __init__(self) -> None:
        super().__init__(raise_error=LLMTimeout())


class UnavailableLLM(FakeLLM):
    def __init__(self) -> None:
        super().__init__(raise_error=LLMUnavailable())


class QuotaLLM(FakeLLM):
    """模拟 DeepSeek 返回 HTTP 402：账户余额不足。"""

    def __init__(self) -> None:
        super().__init__(raise_error=LLMQuotaExceeded())
