"""大模型客户端工厂 —— 唯一的“开关闸门”。

为什么要有这一层：
    之前 chat_service 直接 `DeepSeekClient()`，只要环境里存在 API Key，
    意图识别那一步就会偷偷发出一次请求。这属于“隐式依赖”：
    配置里没写要调用模型，但网络请求已经发了。

    现在所有模型调用都必须经过这里，判断依据只有一个：ANSWER_MODE 是否显式为 llm。
    Key 存在与否不构成启用条件——存在只代表“可以用”，不代表“现在要用”。

    knowledge_only 模式下这个函数返回 None，且不会 import DeepSeekClient，
    更不会读 key、建客户端。测试里通过拦截 socket / httpx 证明零外联。
"""

from __future__ import annotations

import logging

from app.llm.base import LLMClient
from app.runtime_mode import effective_llm_enabled

logger = logging.getLogger(__name__)

_llm_disabled_logged = False


def get_llm_client() -> LLMClient | None:
    """返回可用的模型客户端；纯知识库模式或未配置密钥时返回 None。

    判断依据是**运行期有效模式**（用户在页面上选的那个），不是 .env 的静态值。
    否则用户在主页面切到"大语言模型模式"后，这里仍会返回 None，切换就是假的。
    """
    global _llm_disabled_logged
    if not effective_llm_enabled():
        if not _llm_disabled_logged:
            logger.info("回答模式：knowledge_only（不调用任何外部大模型）")
            _llm_disabled_logged = True
        return None

    # 延迟导入：只有显式开启 llm 模式才会加载这个模块
    from app.llm.deepseek_client import DeepSeekClient

    client = DeepSeekClient()
    if not client.configured:
        logger.warning("回答模式为 llm，但未配置 DEEPSEEK_API_KEY，将退回知识库原文回答")
        return None
    return client
