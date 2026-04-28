"""工具函数：模拟智能家居设备的状态变更接口。

每个工具：
- 声明 OpenAI 风格 schema（name / description / parameters）；
- 实际逻辑只修改本地 home_state（dict），无任何外部 IO；
- 返回 {ok, before, after, message} 便于审计。
"""
from __future__ import annotations
from typing import Any, Callable
import copy

from .schema import RiskLevel


# ---------------------------------------------------------------------------
# Tool registry：name -> {"fn": callable, "schema": dict, "risk": RiskLevel}
# ---------------------------------------------------------------------------
TOOLS: dict[str, dict] = {}


def _register(name: str, schema: dict, risk: str = RiskLevel.LOW.value):
    def deco(fn: Callable):
        TOOLS[name] = {"fn": fn, "schema": schema, "risk": risk}
        return fn
    return deco


def _get_room(state: dict, location: str) -> dict:
    rooms = state.setdefault("rooms", {})
    return rooms.setdefault(location, {"devices": {}})


def _get_device(state: dict, location: str, device: str) -> dict:
    return _get_room(state, location).setdefault("devices", {}).setdefault(device, {})


# --- 灯 -------------------------------------------------------------------
@_register(
    "control_light",
    {
        "name": "control_light",
        "description": "控制指定房间的灯（开 / 关 / 调亮度）。亮度 0-100。",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "房间名"},
                "action": {"type": "string", "enum": ["on", "off", "set"]},
                "brightness": {"type": "number", "minimum": 0, "maximum": 100},
            },
            "required": ["location", "action"],
        },
    },
    risk=RiskLevel.LOW.value,
)
def control_light(state: dict, location: str, action: str, brightness: float | None = None):
    before = copy.deepcopy(_get_device(state, location, "light"))
    dev = _get_device(state, location, "light")
    if action == "on":
        dev["power"] = "on"
        dev.setdefault("brightness", 80)
    elif action == "off":
        dev["power"] = "off"
    elif action == "set" and brightness is not None:
        dev["power"] = "on"
        dev["brightness"] = max(0, min(100, brightness))
    return {"ok": True, "before": before, "after": copy.deepcopy(dev),
            "message": f"{location}灯 {action}"}


# --- 空调 -----------------------------------------------------------------
@_register(
    "control_ac",
    {
        "name": "control_ac",
        "description": "控制空调（开关 / 设置温度 / 调节模式）。",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string"},
                "action": {"type": "string", "enum": ["on", "off", "set_temp"]},
                "temperature": {"type": "number", "minimum": 16, "maximum": 30},
                "mode": {"type": "string", "enum": ["cool", "heat", "auto", "dry"]},
            },
            "required": ["location", "action"],
        },
    },
    risk=RiskLevel.LOW.value,
)
def control_ac(state: dict, location: str, action: str,
               temperature: float | None = None, mode: str | None = None):
    before = copy.deepcopy(_get_device(state, location, "ac"))
    dev = _get_device(state, location, "ac")
    if action == "on":
        dev["power"] = "on"
        dev.setdefault("temp", 26)
        dev.setdefault("mode", mode or "auto")
    elif action == "off":
        dev["power"] = "off"
    elif action == "set_temp" and temperature is not None:
        dev["power"] = "on"
        dev["temp"] = max(16, min(30, temperature))
        if mode:
            dev["mode"] = mode
    return {"ok": True, "before": before, "after": copy.deepcopy(dev),
            "message": f"{location}空调 {action}"}


# --- 窗帘 -----------------------------------------------------------------
@_register(
    "control_curtain",
    {
        "name": "control_curtain",
        "description": "控制窗帘开合。",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string"},
                "action": {"type": "string", "enum": ["open", "close"]},
            },
            "required": ["location", "action"],
        },
    },
    risk=RiskLevel.LOW.value,
)
def control_curtain(state: dict, location: str, action: str):
    before = copy.deepcopy(_get_device(state, location, "curtain"))
    dev = _get_device(state, location, "curtain")
    dev["status"] = "opened" if action == "open" else "closed"
    return {"ok": True, "before": before, "after": copy.deepcopy(dev),
            "message": f"{location}窗帘 {action}"}


# --- 电视 -----------------------------------------------------------------
@_register(
    "control_tv",
    {
        "name": "control_tv",
        "description": "电视开关。",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string"},
                "action": {"type": "string", "enum": ["on", "off"]},
            },
            "required": ["location", "action"],
        },
    },
    risk=RiskLevel.LOW.value,
)
def control_tv(state: dict, location: str, action: str):
    before = copy.deepcopy(_get_device(state, location, "tv"))
    dev = _get_device(state, location, "tv")
    dev["power"] = "on" if action == "on" else "off"
    return {"ok": True, "before": before, "after": copy.deepcopy(dev),
            "message": f"{location}电视 {action}"}


# --- 音响 -----------------------------------------------------------------
@_register(
    "play_music",
    {
        "name": "play_music",
        "description": "在指定房间的音响播放或停止音乐。",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string"},
                "action": {"type": "string", "enum": ["play", "stop"]},
                "playlist": {"type": "string"},
            },
            "required": ["location", "action"],
        },
    },
    risk=RiskLevel.LOW.value,
)
def play_music(state: dict, location: str, action: str, playlist: str | None = None):
    before = copy.deepcopy(_get_device(state, location, "speaker"))
    dev = _get_device(state, location, "speaker")
    dev["power"] = "on" if action == "play" else "off"
    if playlist:
        dev["playlist"] = playlist
    return {"ok": True, "before": before, "after": copy.deepcopy(dev),
            "message": f"{location}音响 {action}"}


# --- 入户门锁（中风险）----------------------------------------------------
@_register(
    "control_door_lock",
    {
        "name": "control_door_lock",
        "description": "解锁或上锁入户门。解锁动作需要二次确认。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["lock", "unlock"]},
            },
            "required": ["action"],
        },
    },
    risk=RiskLevel.MEDIUM.value,
)
def control_door_lock(state: dict, action: str):
    before = copy.deepcopy(state.get("door_lock", {}))
    state["door_lock"] = {"status": "unlocked" if action == "unlock" else "locked"}
    return {"ok": True, "before": before, "after": state["door_lock"],
            "message": f"入户门 {action}"}


# --- 燃气阀（高风险）-----------------------------------------------------
@_register(
    "control_gas_valve",
    {
        "name": "control_gas_valve",
        "description": "燃气总阀开关。高风险操作，必须二次确认。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["open", "close"]},
            },
            "required": ["action"],
        },
    },
    risk=RiskLevel.HIGH.value,
)
def control_gas_valve(state: dict, action: str):
    before = copy.deepcopy(state.get("gas_valve", {}))
    state["gas_valve"] = {"status": "open" if action == "open" else "closed"}
    return {"ok": True, "before": before, "after": state["gas_valve"],
            "message": f"燃气阀 {action}"}


# --- 扫地机 ---------------------------------------------------------------
@_register(
    "control_robot_cleaner",
    {
        "name": "control_robot_cleaner",
        "description": "扫地机器人启动 / 暂停 / 回充。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["start", "pause", "dock"]},
            },
            "required": ["action"],
        },
    },
    risk=RiskLevel.LOW.value,
)
def control_robot_cleaner(state: dict, action: str):
    before = copy.deepcopy(state.get("robot_cleaner", {}))
    state["robot_cleaner"] = {"status": action}
    return {"ok": True, "before": before, "after": state["robot_cleaner"],
            "message": f"扫地机 {action}"}


# --- 提醒 -----------------------------------------------------------------
@_register(
    "send_reminder",
    {
        "name": "send_reminder",
        "description": "向家庭成员发送提醒（吃药、起床、学习检查等）。",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "content": {"type": "string"},
                "channel": {"type": "string", "enum": ["voice", "screen", "both"]},
            },
            "required": ["to", "content"],
        },
    },
    risk=RiskLevel.LOW.value,
)
def send_reminder(state: dict, to: str, content: str, channel: str = "voice"):
    log = state.setdefault("reminder_log", [])
    item = {"to": to, "content": content, "channel": channel}
    log.append(item)
    return {"ok": True, "before": None, "after": item,
            "message": f"已向 {to} 发送提醒：{content}"}


# --- 空气净化器 ----------------------------------------------------------
@_register(
    "control_air_purifier",
    {
        "name": "control_air_purifier",
        "description": "空气净化器开关、风速。",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string"},
                "action": {"type": "string", "enum": ["on", "off"]},
                "speed": {"type": "string", "enum": ["low", "mid", "high", "auto"]},
            },
            "required": ["location", "action"],
        },
    },
    risk=RiskLevel.LOW.value,
)
def control_air_purifier(state: dict, location: str, action: str,
                          speed: str = "auto"):
    before = copy.deepcopy(_get_device(state, location, "air_purifier"))
    dev = _get_device(state, location, "air_purifier")
    dev["power"] = "on" if action == "on" else "off"
    dev["speed"] = speed
    return {"ok": True, "before": before, "after": copy.deepcopy(dev),
            "message": f"{location}空气净化器 {action}"}


# --- 加湿器 --------------------------------------------------------------
@_register(
    "control_humidifier",
    {
        "name": "control_humidifier",
        "description": "加湿器开关、目标湿度。",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string"},
                "action": {"type": "string", "enum": ["on", "off"]},
                "target_humidity": {"type": "number", "minimum": 30, "maximum": 70},
            },
            "required": ["location", "action"],
        },
    },
    risk=RiskLevel.LOW.value,
)
def control_humidifier(state: dict, location: str, action: str,
                        target_humidity: float | None = None):
    before = copy.deepcopy(_get_device(state, location, "humidifier"))
    dev = _get_device(state, location, "humidifier")
    dev["power"] = "on" if action == "on" else "off"
    if target_humidity is not None:
        dev["target_humidity"] = target_humidity
    return {"ok": True, "before": before, "after": copy.deepcopy(dev),
            "message": f"{location}加湿器 {action}"}


# --- 新风系统 ------------------------------------------------------------
@_register(
    "control_fresh_air",
    {
        "name": "control_fresh_air",
        "description": "新风系统开关、档位。",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string"},
                "action": {"type": "string", "enum": ["on", "off"]},
                "level": {"type": "string", "enum": ["low", "mid", "high"]},
            },
            "required": ["location", "action"],
        },
    },
    risk=RiskLevel.LOW.value,
)
def control_fresh_air(state: dict, location: str, action: str,
                       level: str = "mid"):
    before = copy.deepcopy(_get_device(state, location, "fresh_air"))
    dev = _get_device(state, location, "fresh_air")
    dev["power"] = "on" if action == "on" else "off"
    dev["level"] = level
    return {"ok": True, "before": before, "after": copy.deepcopy(dev),
            "message": f"{location}新风 {action}"}


# --- 热水器 --------------------------------------------------------------
@_register(
    "control_water_heater",
    {
        "name": "control_water_heater",
        "description": "热水器开关、目标温度。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["on", "off"]},
                "temperature": {"type": "number", "minimum": 35, "maximum": 75},
            },
            "required": ["action"],
        },
    },
    risk=RiskLevel.MEDIUM.value,
)
def control_water_heater(state: dict, action: str,
                          temperature: float | None = None):
    before = copy.deepcopy(state.get("water_heater", {}))
    state["water_heater"] = {"power": "on" if action == "on" else "off"}
    if temperature is not None:
        state["water_heater"]["temperature"] = temperature
    return {"ok": True, "before": before, "after": state["water_heater"],
            "message": f"热水器 {action}"}


# --- 安全巡检（查询型工具）-------------------------------------------------
@_register(
    "security_check",
    {
        "name": "security_check",
        "description": "对门锁、燃气阀、窗户、摄像头进行一次安全巡检。",
        "parameters": {
            "type": "object",
            "properties": {
                "scope": {"type": "string", "enum": ["door", "gas", "window",
                                                       "camera", "all"]},
            },
        },
    },
    risk=RiskLevel.LOW.value,
)
def security_check(state: dict, scope: str = "all"):
    door = state.get("door_lock", {}).get("status", "unknown")
    gas = state.get("gas_valve", {}).get("status", "unknown")
    issues: list[str] = []
    if door != "locked":
        issues.append("入户门未锁")
    if gas == "open":
        issues.append("燃气阀仍开启（夜间/离家建议关闭）")
    summary = "全部正常" if not issues else "发现 " + "；".join(issues)
    item = {"scope": scope, "door": door, "gas": gas,
             "issues": issues, "summary": summary}
    return {"ok": True, "before": None, "after": item,
            "message": f"安全巡检：{summary}"}


# --- 紧急呼叫（关怀场景核心）---------------------------------------------
@_register(
    "emergency_call",
    {
        "name": "emergency_call",
        "description": "向家属或紧急联系人发起呼叫（家人摔倒等紧急场景）。",
        "parameters": {
            "type": "object",
            "properties": {
                "contact": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["contact", "reason"],
        },
    },
    risk=RiskLevel.MEDIUM.value,
)
def emergency_call(state: dict, contact: str, reason: str):
    log = state.setdefault("call_log", [])
    item = {"contact": contact, "reason": reason}
    log.append(item)
    return {"ok": True, "before": None, "after": item,
            "message": f"已呼叫 {contact}：{reason}"}


def get_tool_schemas() -> list[dict]:
    return [v["schema"] for v in TOOLS.values()]


def get_tool_risk(name: str) -> str:
    return TOOLS.get(name, {}).get("risk", RiskLevel.LOW.value)


def call_tool(name: str, state: dict, **kwargs) -> dict:
    if name not in TOOLS:
        return {"ok": False, "message": f"未知工具：{name}"}
    fn = TOOLS[name]["fn"]
    try:
        return fn(state, **kwargs)
    except TypeError as e:
        return {"ok": False, "message": f"参数错误：{e}"}
    except Exception as e:
        return {"ok": False, "message": f"执行异常：{e}"}
