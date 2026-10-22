"""运行期回答模式。

为什么不能只读 settings.answer_mode：
    `settings` 是启动时从 .env 解析出来的单例。用户在主页面点一下
    “大语言模型模式”，如果只改这个对象的属性，重启就丢了；
    而如果只在前端存 localStorage，后端实际仍在按旧模式执行——
    那就是“界面假装切换了”，属于欺骗。

这里的做法：
    .env 的 ANSWER_MODE = **默认值**；
    用户在页面上的选择 = **覆盖值**，落库（app_settings 表），进程内缓存。
    每次判断都走 effective_answer_mode()，所以切换是立刻生效的。

作用域：全局。所有会话共用同一个模式，不做“每个会话独立模式”。
这是有意为之——模式决定的是“这台机器上的进程允不允许调外部模型”，
不是某一轮对话的偏好。UI 上必须写清楚这一点。

安全性：即使 effective_mode 是 llm，只要没有密钥，effective_llm_ready()
仍为 False，chat_service 会走降级分支，不会发出请求。反过来，
即使环境里躺着有效密钥，模式为 knowledge_only 时也不会有任何外联。
"""

from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)

VALID_MODES: tuple[str, ...] = ("knowledge_only", "llm")

MODE_LABELS: dict[str, str] = {
    "knowledge_only": "知识库模式",
    "llm": "大语言模型模式",
}

# 用户在页面上做的显式选择；None 表示“没改过，用 .env 的默认值”
_override: str | None = None


def normalize_mode(mode: str | None) -> str | None:
    """统一小写去空格；非法值返回 None，由调用方决定报错还是忽略。"""
    if mode is None:
        return None
    value = str(mode).strip().lower()
    return value if value in VALID_MODES else None


def effective_answer_mode() -> str:
    """当前真正生效的模式。"""
    return _override or settings.answer_mode


def effective_llm_enabled() -> bool:
    """是否允许调用大模型。只看模式，不看密钥是否齐全。"""
    return effective_answer_mode() == "llm"


def effective_llm_ready() -> bool:
    """是否可能真的发出请求：模式已开启 **且** 密钥已配置。"""
    return effective_llm_enabled() and settings.llm_configured


def current_override() -> str | None:
    return _override


def set_override(mode: str | None) -> None:
    """设置/清除运行期覆盖值（仅内存；落库由 settings_service 负责）。"""
    global _override
    if mode is not None:
        normalized = normalize_mode(mode)
        if normalized is None:
            raise ValueError(f"不支持的运行模式：{mode}")
        mode = normalized
    _override = mode
    logger.info("回答模式覆盖值已更新：%s（生效值：%s）", mode, effective_answer_mode())


def reset_override() -> None:
    """测试专用：回到“只用 .env 默认值”的状态。"""
    global _override
    _override = None
