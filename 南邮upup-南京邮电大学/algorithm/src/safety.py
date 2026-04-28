"""安全约束：静态规则 + 动态二次确认。

输入：候选 ToolCall 列表 + 当前 home_state + user_profile + 当前时间。
输出：每条 ToolCall 一份 SafetyVerdict；如有 high 风险动作，整个会话置位 requires_confirmation。
"""
from __future__ import annotations
from datetime import datetime
from typing import Iterable

from .schema import ToolCall, SafetyVerdict, RiskLevel
from .tools import get_tool_risk


# 时段策略：深夜不允许打开高功率设备
_QUIET_HOURS = (23, 7)  # 23:00 - 07:00


def _in_quiet_hours(now: datetime) -> bool:
    h = now.hour
    start, end = _QUIET_HOURS
    if start < end:
        return start <= h < end
    return h >= start or h < end


def evaluate(tool_call: ToolCall, home_state: dict, user_profile: dict,
             now: datetime | None = None) -> SafetyVerdict:
    now = now or datetime.now()
    risk = get_tool_risk(tool_call.name)

    # 高风险：必须二次确认
    if risk == RiskLevel.HIGH.value:
        return SafetyVerdict(
            allowed=False,
            risk_level=risk,
            requires_confirmation=True,
            reason="高风险设备操作（燃气 / 安防 / 总闸），需用户二次确认。",
        )

    # 中风险：默认要求确认，除非是紧急关怀场景（emergency_call/紧急解锁）
    if risk == RiskLevel.MEDIUM.value:
        emergency = bool(home_state.get("emergency_active"))
        if emergency:
            return SafetyVerdict(
                allowed=True, risk_level=risk, requires_confirmation=False,
                reason="紧急关怀场景已激活，跳过二次确认以争取救援时间。",
            )
        return SafetyVerdict(
            allowed=False, risk_level=risk, requires_confirmation=True,
            reason="中风险动作（开门 / 紧急呼叫等）默认需确认。",
        )

    # 低风险：检查时段
    if _in_quiet_hours(now):
        # 深夜禁止启动高分贝设备
        if tool_call.name in {"play_music", "control_robot_cleaner"} and \
                tool_call.arguments.get("action") in {"play", "start"}:
            return SafetyVerdict(
                allowed=False, risk_level=risk, requires_confirmation=True,
                reason=f"当前为深夜时段({now.hour:02d}:00)，启动该设备可能扰民，需确认。",
            )

    # 全屋类操作：可作为低风险，但记录
    return SafetyVerdict(
        allowed=True, risk_level=risk, requires_confirmation=False,
        reason="低风险操作，自动执行。",
    )


def evaluate_all(tool_calls: Iterable[ToolCall], home_state: dict, user_profile: dict,
                 now: datetime | None = None) -> tuple[list[SafetyVerdict], bool]:
    verdicts = [evaluate(tc, home_state, user_profile, now) for tc in tool_calls]
    needs_conf = any(v.requires_confirmation for v in verdicts)
    return verdicts, needs_conf
