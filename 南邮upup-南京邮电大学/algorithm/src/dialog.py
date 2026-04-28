"""多轮对话状态机：管理 pending 待确认动作、上下文消解、澄清提问。

每个 session 维护：
- pending_plan：上一轮被安全模块挂起的计划（等待用户"确认/取消"）
- last_intent / last_slots：用于"再低一点"这类指代消解
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from .schema import Intent, Slots, PlanStep


@dataclass
class SessionState:
    session_id: str
    pending_plan: list[PlanStep] = field(default_factory=list)
    last_intent: Optional[Intent] = None
    last_slots: Optional[Slots] = None
    history: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "pending_plan": [s.to_dict() for s in self.pending_plan],
            "last_intent": self.last_intent.to_dict() if self.last_intent else None,
            "last_slots": self.last_slots.to_dict() if self.last_slots else None,
            "history": self.history,
        }


# 进程内缓存：session_id -> SessionState
_SESSIONS: dict[str, SessionState] = {}


def get_session(sid: str) -> SessionState:
    if sid not in _SESSIONS:
        _SESSIONS[sid] = SessionState(session_id=sid)
    return _SESSIONS[sid]


def reset_session(sid: str):
    _SESSIONS.pop(sid, None)


def merge_slots(prev: Optional[Slots], cur: Slots) -> Slots:
    """指代消解：如果当前槽位缺失某字段，从上一轮补齐。"""
    if prev is None:
        return cur
    out = Slots(
        location=cur.location or prev.location,
        device=cur.device or prev.device,
        action=cur.action or prev.action,
        value=cur.value if cur.value is not None else prev.value,
        member=cur.member or prev.member,
        time=cur.time or prev.time,
    )
    out.extras = {**prev.extras, **cur.extras}
    return out
