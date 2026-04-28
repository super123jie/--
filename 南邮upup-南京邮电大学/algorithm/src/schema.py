"""数据契约：意图 / 槽位 / 计划 / 工具调用 / 最终响应的结构定义。

所有结构都设计为可 JSON 序列化，便于前后端对接、日志审计、答辩演示。
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Optional
from enum import Enum


class RiskLevel(str, Enum):
    LOW = "low"        # 灯光、窗帘、空调温度调节、播放音乐
    MEDIUM = "medium"  # 入户门解锁、扫地机出库、热水器开启
    HIGH = "high"      # 燃气阀、监控录像导出、安防布撤防、电源总闸


class IntentName(str, Enum):
    # 场景模式
    MODE_SLEEP = "mode.sleep"           # 睡眠模式
    MODE_LEAVE = "mode.leave"           # 离家模式
    MODE_HOME = "mode.home"             # 回家模式
    MODE_ENERGY = "mode.energy_save"    # 节能模式
    MODE_PARTY = "mode.party"
    MODE_MOVIE = "mode.movie"           # 观影 / 影院 / 追剧
    MODE_STUDY = "mode.study"           # 学习模式（儿童学习/网课）           # 聚会模式
    # 设备控制
    DEVICE_LIGHT = "device.light"
    DEVICE_AC = "device.ac"
    DEVICE_CURTAIN = "device.curtain"
    DEVICE_TV = "device.tv"
    DEVICE_SPEAKER = "device.speaker"
    DEVICE_LOCK = "device.lock"
    DEVICE_GAS = "device.gas_valve"
    DEVICE_ROBOT = "device.robot_cleaner"
    DEVICE_AIR_PURIFIER = "device.air_purifier"   # 空气净化器
    DEVICE_HUMIDIFIER = "device.humidifier"       # 加湿器
    DEVICE_FRESH_AIR = "device.fresh_air"         # 新风系统
    DEVICE_WATER_HEATER = "device.water_heater"   # 热水器
    # 关怀功能
    CARE_MEDICINE = "care.medicine_remind"
    CARE_STUDY = "care.child_study_check"
    CARE_FALL = "care.fall_emergency"
    CARE_NIGHT = "care.night_companion"
    CARE_WATER = "care.water_remind"              # 提醒喝水
    CARE_GENERAL_ELDER = "care.elder_general"     # 老人通用关怀
    CARE_EYE_BREAK = "care.eye_break"             # 提醒孩子休息眼睛
    # 安全事件预案（V4 新增）
    SAFETY_GAS_LEAK = "safety.gas_leak"           # 闻到煤气味 / 燃气泄漏
    SAFETY_ELDER_NO_RESP = "safety.elder_no_response"  # 老人无响应
    SAFETY_CHILD_ALONE = "safety.child_alone"     # 儿童独自在家
    SAFETY_DOOR_ANOMALY = "safety.door_anomaly"   # 门窗异常
    SAFETY_INTRUSION = "safety.night_intrusion"   # 夜间陌生开门
    # 信息查询
    QUERY_STATUS = "query.status"
    QUERY_PREFERENCE = "query.preference"
    QUERY_SECURITY_CHECK = "query.security_check"  # 安全巡检/安防检查
    # 多轮对话
    DIALOG_CONFIRM = "dialog.confirm"
    DIALOG_CANCEL = "dialog.cancel"
    DIALOG_CLARIFY = "dialog.clarify"
    # 兜底
    UNKNOWN = "unknown"


@dataclass
class Intent:
    name: str
    confidence: float
    raw: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Slots:
    location: Optional[str] = None        # 卧室 / 客厅 / 厨房 / 全屋
    device: Optional[str] = None          # 灯 / 空调 / 窗帘
    action: Optional[str] = None          # 开 / 关 / 调高 / 调低
    value: Optional[float] = None         # 温度数值 / 亮度百分比
    member: Optional[str] = None          # 家庭成员（爷爷 / 奶奶 / 小明）
    time: Optional[str] = None            # 时间表述（早上 / 22:00 / 5分钟后）
    extras: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: v for k, v in d.items() if v not in (None, {}, [])}


@dataclass
class ToolCall:
    name: str                              # 工具函数名
    arguments: dict = field(default_factory=dict)
    risk_level: str = RiskLevel.LOW.value
    requires_confirmation: bool = False
    rationale: str = ""                    # 解释为什么调用，便于答辩展示

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PlanStep:
    step_id: int
    description: str
    tool_call: Optional[ToolCall] = None
    depends_on: list = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {"step_id": self.step_id, "description": self.description, "depends_on": self.depends_on}
        if self.tool_call is not None:
            d["tool_call"] = self.tool_call.to_dict()
        return d


@dataclass
class SafetyVerdict:
    allowed: bool
    risk_level: str
    requires_confirmation: bool
    reason: str = ""


@dataclass
class AgentResponse:
    """主响应对象：run() 函数的统一返回结构。"""
    user_input: str
    intent: dict
    slots: dict
    plan: list                             # list[PlanStep.to_dict()]
    safety: list                           # list[SafetyVerdict 序列化]
    tool_results: list                     # 工具实际执行返回
    reply: str                             # 给用户的自然语言反馈
    requires_confirmation: bool
    home_state_after: dict
    timing_ms: dict                        # 各阶段耗时
    session_id: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
