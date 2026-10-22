"""运行期设置（目前只有回答模式）的读写。

写入流程刻意做成"先落库、再改内存"：
    如果先改内存后写库，写库失败时进程内的模式和库里不一致，
    重启后用户会看到自己"切回去了"，很难解释。
    反过来先写库、再更新内存，最坏情况是库里改了内存没改（几乎不会发生，
    因为内存赋值不会失败），而且下次启动读库就自动纠正。
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session as OrmSession

from app.config import settings
from app.db.models import AppSetting
from app.runtime_mode import (
    MODE_LABELS,
    VALID_MODES,
    current_override,
    effective_answer_mode,
    normalize_mode,
    set_override,
)

logger = logging.getLogger(__name__)

ANSWER_MODE_KEY = "answer_mode"


class InvalidModeError(ValueError):
    """模式值不合法。路由层转成 422，而不是默默忽略。"""


def load_answer_mode(db: OrmSession) -> None:
    """启动时把库里的覆盖值读进内存。没有记录就保持 .env 默认值。"""
    row = db.get(AppSetting, ANSWER_MODE_KEY)
    if row is None:
        set_override(None)
        return
    normalized = normalize_mode(row.value)
    if normalized is None:
        logger.warning("数据库中的回答模式 %r 不合法，已忽略并回退默认值", row.value)
        set_override(None)
        return
    set_override(normalized)


def save_answer_mode(db: OrmSession, mode: str) -> str:
    """校验并保存模式，返回实际生效的值。"""
    normalized = normalize_mode(mode)
    if normalized is None:
        raise InvalidModeError(f"不支持的运行模式：{mode}")

    row = db.get(AppSetting, ANSWER_MODE_KEY)
    if row is None:
        row = AppSetting(key=ANSWER_MODE_KEY, value=normalized)
        db.add(row)
    else:
        row.value = normalized
    db.commit()
    set_override(normalized)
    logger.info("回答模式已切换为 %s（已持久化）", normalized)
    return normalized


def answer_mode_state(db: OrmSession) -> dict:
    """给接口用的完整状态：当前值、来源、是否持久化、默认值、可选项。"""
    row = db.get(AppSetting, ANSWER_MODE_KEY)
    mode = effective_answer_mode()
    return {
        "mode": mode,
        "label": MODE_LABELS.get(mode, mode),
        "scope": "global",
        "scope_note": "回答模式为全局设置，对所有会话生效；重启后端仍保留，"
        "将 .env 的 ANSWER_MODE 作为默认值。",
        "default_mode": settings.answer_mode,
        "overridden": current_override() is not None,
        "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
        "options": [
            {
                "value": "knowledge_only",
                "label": MODE_LABELS["knowledge_only"],
                "description": "仅使用本地规则与知识库检索，不调用外部大模型 API。",
            },
            {
                "value": "llm",
                "label": MODE_LABELS["llm"],
                "description": "优先检索知识库，再由已配置的大语言模型组织回答；"
                "模型不可用时按安全规则降级为知识库原文。",
            },
        ],
        "valid_values": list(VALID_MODES),
    }
