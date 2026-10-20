"""模型客户端抽象。

为什么要抽象？
    业务层只关心“给我一段回答”，不应该关心 HTTP、超时、重试。
    这样测试时可以直接注入一个假客户端（FakeLLM），不用花真钱调 API。

错误分类很重要：
    不是所有失败都一样。超时可以让用户重试；鉴权失败是配置问题；
    额度不足是运营问题。前端提示语和 HTTP 状态码都应该不同。
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMError(Exception):
    """模型调用失败基类。"""

    code = "llm_error"
    http_status = 502
    user_message = "智能客服暂时不可用，请稍后重试。"


class LLMNotConfigured(LLMError):
    code = "llm_not_configured"
    http_status = 503
    user_message = "后端尚未配置大模型密钥，无法生成智能回答。"


class LLMTimeout(LLMError):
    code = "llm_timeout"
    http_status = 504
    user_message = "回答生成超时，请重试或联系人工客服。"


class LLMUnavailable(LLMError):
    code = "llm_unavailable"
    http_status = 503
    user_message = "大模型服务暂时不可用，请稍后再试。"


class LLMAuthError(LLMError):
    code = "llm_auth_error"
    http_status = 503
    user_message = "大模型服务鉴权失败，请联系管理员检查配置。"


class LLMQuotaExceeded(LLMError):
    """HTTP 402：密钥有效，但账户余额/额度不足。"""

    code = "llm_quota_exceeded"
    http_status = 503
    user_message = "大模型账户余额不足，暂时无法生成回答。"


class LLMClient(ABC):
    name: str = "base"
    model: str = ""

    @abstractmethod
    async def complete(self, messages: list[dict], temperature: float = 0.3) -> str:
        """输入 OpenAI 兼容的消息数组，返回纯文本回答。失败时抛 LLMError 子类。"""
