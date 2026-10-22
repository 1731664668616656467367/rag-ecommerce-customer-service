"""模型调用的运行期状态。

要解决的问题：前端需要知道“模型到底能不能用”，但**不能**靠猜，
也不能靠真的发一次请求去试探（那会花钱、还会有延迟）。

这里记录**最近一次真实调用**的结果，前端读这个快照：
    - 从没调用过 → status=unverified（已配置密钥，但尚未验证）
    - 最近一次成功 → status=ok
    - 最近一次失败 → status=error + 人类可读的原因（如余额不足 402）

这样“模型可用”四个字永远有证据支撑，不会变成一句空口号。
"""

from __future__ import annotations

from datetime import datetime, timezone

# 失败码 → 给用户看的说明。刻意不暴露任何密钥、URL 或内部堆栈。
FAILURE_TEXT: dict[str, str] = {
    "llm_quota_exceeded": "模型账户余额不足或已达到额度限制（HTTP 402）",
    "llm_timeout": "模型服务响应超时",
    "llm_unavailable": "模型服务当前不可用（网络异常或服务端错误）",
    "llm_not_configured": "尚未配置可用的模型服务",
    "llm_auth_error": "模型服务鉴权失败，请检查密钥是否有效",
}

_state: dict = {
    "last_failure": None,  # {"code": str, "text": str, "at": str}
    "last_success_at": None,
    "failures": 0,
    "successes": 0,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record_failure(code: str, detail: str = "") -> None:
    _state["last_failure"] = {
        "code": code,
        "text": FAILURE_TEXT.get(code, "模型调用失败"),
        "at": _now(),
        # detail 只用于后端日志，不返回给前端
    }
    _state["failures"] += 1


def record_success() -> None:
    _state["last_success_at"] = _now()
    _state["successes"] += 1
    # 成功后清掉上一次失败，避免界面一直显示过期错误
    _state["last_failure"] = None


def snapshot() -> dict:
    return {
        "last_failure": dict(_state["last_failure"]) if _state["last_failure"] else None,
        "last_success_at": _state["last_success_at"],
        "failures": _state["failures"],
        "successes": _state["successes"],
    }


def reset() -> None:
    """测试专用。"""
    _state.update(
        {"last_failure": None, "last_success_at": None, "failures": 0, "successes": 0}
    )
