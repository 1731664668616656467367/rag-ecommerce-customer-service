"""运行模式接口：读取当前模式、切换模式。

为什么单独一个路由文件而不是塞进 health：
    health 是**只读观测**接口，模式切换是**会改状态**的操作。
    混在一起会让"健康检查"带上副作用，缓存、监控、探活都会出问题。

安全边界：
    - 响应里只有 provider / model 名称、是否配置、最近一次失败原因；
    - 密钥、base_url、内部堆栈一律不出现；
    - 前端无法通过任何字段反推出密钥内容。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as OrmSession

from app.config import settings
from app.db.session import get_db
from app.llm import status as llm_status
from app.runtime_mode import effective_answer_mode, effective_llm_ready
from app.schemas.models import AnswerModeResponse, AnswerModeUpdate
from app.services import settings_service
from app.services.settings_service import InvalidModeError

router = APIRouter(tags=["settings"])


def _model_status() -> dict:
    """按"有没有配置 / 有没有真的调用过"给出可核验的状态。"""
    configured = settings.llm_configured
    snap = llm_status.snapshot()
    failure = snap["last_failure"]

    if not configured:
        status = "not_configured"
        text = "尚未配置可用的模型服务（后端未设置 DEEPSEEK_API_KEY）"
    elif failure:
        status = "error"
        text = failure["text"]
    elif snap["last_success_at"]:
        status = "ok"
        text = "最近一次调用成功"
    else:
        status = "unverified"
        text = "已配置密钥，尚未发起过调用（不代表一定可用）"

    return {
        "provider": "deepseek",
        "model": settings.deepseek_model,
        "configured": configured,
        "status": status,
        "status_text": text,
        "will_be_called": effective_llm_ready(),
        "last_failure": failure,
        "last_success_at": snap["last_success_at"],
    }


def _payload(db: OrmSession) -> AnswerModeResponse:
    state = settings_service.answer_mode_state(db)
    return AnswerModeResponse(**state, model=_model_status())


@router.get("/settings/answer-mode", response_model=AnswerModeResponse)
def read_answer_mode(db: OrmSession = Depends(get_db)) -> AnswerModeResponse:
    """当前生效的模式 + 可选项 + 模型服务状态。"""
    return _payload(db)


@router.put("/settings/answer-mode", response_model=AnswerModeResponse)
def update_answer_mode(
    payload: AnswerModeUpdate, db: OrmSession = Depends(get_db)
) -> AnswerModeResponse:
    """切换模式。

    允许切到 llm 即使模型没配置——用户有权表达意图，
    界面会同时显示"当前不可用，回答将降级为知识库原文"。
    拦住反而更糟：用户会以为系统坏了，而不是"没配密钥"。
    """
    try:
        settings_service.save_answer_mode(db, payload.mode)
    except InvalidModeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _payload(db)


@router.post("/settings/answer-mode/reset", response_model=AnswerModeResponse)
def reset_answer_mode(db: OrmSession = Depends(get_db)) -> AnswerModeResponse:
    """清除页面上的覆盖值，回到 .env 的默认模式。"""
    from app.db.models import AppSetting

    row = db.get(AppSetting, settings_service.ANSWER_MODE_KEY)
    if row is not None:
        db.delete(row)
        db.commit()
    from app.runtime_mode import set_override

    set_override(None)
    return _payload(db)


__all__ = ["router", "effective_answer_mode"]
