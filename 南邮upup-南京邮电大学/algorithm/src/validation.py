"""数值边界校验：温度 / 亮度 / 时间。

越界时返回 (False, 警告文案, 建议范围)，由 Planner 决定是请用户确认还是直接拒绝。
"""
from __future__ import annotations
from typing import Optional

LIMITS = {
    "ac_temp": (16, 30, "℃"),
    "brightness": (0, 100, "%"),
}


def validate_temp(value: float | None) -> tuple[bool, Optional[str]]:
    if value is None:
        return True, None
    lo, hi, unit = LIMITS["ac_temp"]
    if not (lo <= value <= hi):
        return False, (f"空调温度应在 {lo}-{hi}{unit} 之间，您输入的 {value}{unit} 超出范围，"
                        f"请重新确认目标温度。")
    return True, None


def validate_brightness(value: float | None) -> tuple[bool, Optional[str]]:
    if value is None:
        return True, None
    lo, hi, unit = LIMITS["brightness"]
    if not (lo <= value <= hi):
        return False, (f"灯光亮度应在 {lo}-{hi}{unit} 之间，您输入的 {value}{unit} 超出范围。")
    return True, None


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
