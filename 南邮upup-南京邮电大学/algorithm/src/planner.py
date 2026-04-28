"""规划层：把 (Intent, Slots, HomeState, UserProfile) 映射成有序的 ToolCall 序列。

规划器使用规则模板（规则即"知识"），针对每个意图给出标准动作序列；
槽位会被填充到具体参数；用户偏好覆盖默认值；安全约束在 safety.py 二次裁决。

为什么选规则模板：
- 端侧 4GB 内存约束下，调用 LLM 做规划会显著增加延迟和资源；
- 智能家居场景的规划路径有限且高度可枚举，规则收益最高、可解释性最强；
- 留接口 plan_with_llm() 给未来 Qwen2.5-0.5B 替换。
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional

from .schema import Intent, Slots, ToolCall, PlanStep, IntentName, RiskLevel
from .tools import TOOLS, get_tool_risk
from .validation import validate_temp, validate_brightness, clamp


# ---------------------------------------------------------------------------
# 帮助函数
# ---------------------------------------------------------------------------
def _tool(name: str, args: dict, rationale: str = "") -> ToolCall:
    return ToolCall(
        name=name, arguments=args,
        risk_level=get_tool_risk(name),
        requires_confirmation=False,  # safety.py 会重写
        rationale=rationale,
    )


def _get_pref(profile: dict, key: str, default):
    return (profile or {}).get("preferences", {}).get(key, default)


def _all_rooms(state: dict) -> list[str]:
    return list(state.get("rooms", {}).keys())


# ---------------------------------------------------------------------------
# 各意图的规划函数
# ---------------------------------------------------------------------------
def _plan_sleep(slots: Slots, state: dict, profile: dict) -> list[ToolCall]:
    sleep_temp = _get_pref(profile, "sleep_temp", 25)
    night_brt = _get_pref(profile, "preferred_light_brightness_night", 15)
    calls: list[ToolCall] = []
    for room in _all_rooms(state):
        # 主卧保留夜灯，其它房间灯全关
        if room == "主卧":
            calls.append(_tool("control_light", {"location": room, "action": "set",
                                                  "brightness": night_brt},
                                rationale="主卧保留夜灯方便起夜"))
        else:
            calls.append(_tool("control_light", {"location": room, "action": "off"},
                                rationale="睡眠时关闭非主卧灯光"))
        if "ac" in state["rooms"][room].get("devices", {}):
            calls.append(_tool("control_ac", {"location": room, "action": "set_temp",
                                               "temperature": sleep_temp, "mode": "auto"},
                                rationale=f"按用户偏好将空调调至 {sleep_temp}℃"))
        if "curtain" in state["rooms"][room].get("devices", {}):
            calls.append(_tool("control_curtain", {"location": room, "action": "close"},
                                rationale="拉上窗帘营造睡眠环境"))
        if "tv" in state["rooms"][room].get("devices", {}):
            calls.append(_tool("control_tv", {"location": room, "action": "off"},
                                rationale="关闭电视"))
        if "speaker" in state["rooms"][room].get("devices", {}):
            calls.append(_tool("play_music", {"location": room, "action": "stop"},
                                rationale="停止播放"))
    calls.append(_tool("control_door_lock", {"action": "lock"},
                       rationale="入睡前锁门保障安全（中风险，需确认）"))
    return calls


def _plan_leave(slots: Slots, state: dict, profile: dict) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for room in _all_rooms(state):
        calls.append(_tool("control_light", {"location": room, "action": "off"},
                            rationale="离家关闭所有灯"))
        if "ac" in state["rooms"][room].get("devices", {}):
            calls.append(_tool("control_ac", {"location": room, "action": "off"},
                                rationale="离家关闭空调节能"))
        if "tv" in state["rooms"][room].get("devices", {}):
            calls.append(_tool("control_tv", {"location": room, "action": "off"},
                                rationale="关闭电视"))
        if "speaker" in state["rooms"][room].get("devices", {}):
            calls.append(_tool("play_music", {"location": room, "action": "stop"},
                                rationale="停止播放"))
    calls.append(_tool("control_door_lock", {"action": "lock"},
                       rationale="离家自动上锁"))
    calls.append(_tool("control_gas_valve", {"action": "close"},
                       rationale="关闭燃气总阀（高风险，必须确认）"))
    return calls


def _plan_home(slots: Slots, state: dict, profile: dict) -> list[ToolCall]:
    wake_temp = _get_pref(profile, "wake_temp", 24)
    return [
        _tool("control_door_lock", {"action": "unlock"},
              rationale="回家解锁入户门（中风险）"),
        _tool("control_light", {"location": "玄关", "action": "on"},
              rationale="点亮玄关灯"),
        _tool("control_light", {"location": "客厅", "action": "set", "brightness": 80},
              rationale="客厅灯亮起"),
        _tool("control_ac", {"location": "客厅", "action": "set_temp",
                              "temperature": wake_temp, "mode": "auto"},
              rationale=f"客厅空调启动至偏好温度 {wake_temp}℃"),
        _tool("play_music", {"location": "客厅", "action": "play",
                              "playlist": _get_pref(profile, "music_genre", "轻音乐")},
              rationale="播放偏好音乐"),
    ]


def _plan_energy(slots: Slots, state: dict, profile: dict) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for room, info in state.get("rooms", {}).items():
        devs = info.get("devices", {})
        if devs.get("light", {}).get("power") == "on":
            calls.append(_tool("control_light", {"location": room, "action": "set",
                                                  "brightness": 50},
                                rationale="亮度降至50%节能"))
        if devs.get("ac", {}).get("power") == "on":
            cur = devs["ac"].get("temp", 26)
            target = max(16, min(30, cur + 1))  # 制冷模式调高1度更省电
            calls.append(_tool("control_ac", {"location": room, "action": "set_temp",
                                               "temperature": target},
                                rationale=f"空调温度上调至 {target}℃ 节能"))
    return calls


def _plan_movie(slots: Slots, state: dict, profile: dict) -> list[ToolCall]:
    """观影模式：客厅灯调暗、拉窗帘、开电视、音响调到舒适音量。"""
    return [
        _tool("control_light", {"location": "客厅", "action": "set", "brightness": 20},
              rationale="客厅灯调至 20% 营造影院氛围"),
        _tool("control_curtain", {"location": "客厅", "action": "close"},
              rationale="拉上客厅窗帘减少反光"),
        _tool("control_tv", {"location": "客厅", "action": "on"},
              rationale="打开电视"),
        _tool("play_music", {"location": "客厅", "action": "play",
                              "playlist": "影院环绕声"},
              rationale="启动环绕音响"),
    ]


def _plan_study(slots: Slots, state: dict, profile: dict) -> list[ToolCall]:
    """学习模式：儿童房灯调亮、客厅电视/音响关闭、新风开。"""
    return [
        _tool("control_light", {"location": "儿童房", "action": "set", "brightness": 90},
              rationale="儿童房灯调亮，护眼读写"),
        _tool("control_tv", {"location": "客厅", "action": "off"},
              rationale="关闭客厅电视避免干扰"),
        _tool("play_music", {"location": "客厅", "action": "stop"},
              rationale="停止音乐"),
        _tool("control_ac", {"location": "儿童房", "action": "set_temp",
                              "temperature": 25, "mode": "auto"},
              rationale="儿童房空调保持舒适温度"),
        _tool("send_reminder",
              {"to": "小明", "content": "学习模式开启，专注 25 分钟后会提醒你休息眼睛。",
                "channel": "screen"},
              rationale="给孩子提示"),
    ]


def _plan_party(slots: Slots, state: dict, profile: dict) -> list[ToolCall]:
    return [
        _tool("control_light", {"location": "客厅", "action": "set", "brightness": 100},
              rationale="客厅灯调至最亮"),
        _tool("control_curtain", {"location": "客厅", "action": "open"},
              rationale="打开窗帘"),
        _tool("play_music", {"location": "客厅", "action": "play", "playlist": "派对热歌"},
              rationale="播放派对音乐"),
        _tool("control_ac", {"location": "客厅", "action": "set_temp", "temperature": 24},
              rationale="客厅温度调至舒适"),
    ]


def _plan_device(intent: str, slots: Slots, state: dict, profile: dict) -> list[ToolCall]:
    location = slots.location or "客厅"
    action = slots.action

    if intent == IntentName.DEVICE_LIGHT.value:
        if action == "on":
            return [_tool("control_light", {"location": location, "action": "on"},
                          rationale="开灯")]
        if action == "off":
            return [_tool("control_light", {"location": location, "action": "off"},
                          rationale="关灯")]
        if action == "up":
            cur = state.get("rooms", {}).get(location, {}).get("devices", {}).get("light", {}).get("brightness", 50)
            return [_tool("control_light", {"location": location, "action": "set",
                                             "brightness": min(100, cur + 20)},
                          rationale="亮度上调")]
        if action == "down":
            cur = state.get("rooms", {}).get(location, {}).get("devices", {}).get("light", {}).get("brightness", 50)
            return [_tool("control_light", {"location": location, "action": "set",
                                             "brightness": max(0, cur - 20)},
                          rationale="亮度下调")]
        if slots.value is not None:
            return [_tool("control_light", {"location": location, "action": "set",
                                             "brightness": float(slots.value)},
                          rationale=f"亮度设为 {slots.value}")]
        return [_tool("control_light", {"location": location, "action": "on"},
                      rationale="未明确动作，默认开灯")]

    if intent == IntentName.DEVICE_AC.value:
        # 即使越界也先生成调用，由 plan() 末尾的 validate_temp 给出明确警告
        if slots.value is not None:
            return [_tool("control_ac", {"location": location, "action": "set_temp",
                                          "temperature": float(slots.value)},
                          rationale=f"空调温度设为 {slots.value}℃")]
        if action == "on":
            return [_tool("control_ac", {"location": location, "action": "on"},
                          rationale="开空调")]
        if action == "off":
            return [_tool("control_ac", {"location": location, "action": "off"},
                          rationale="关空调")]
        if action in ("up", "down"):
            cur = state.get("rooms", {}).get(location, {}).get("devices", {}).get("ac", {}).get("temp", 26)
            delta = 1 if action == "up" else -1
            return [_tool("control_ac", {"location": location, "action": "set_temp",
                                          "temperature": max(16, min(30, cur + delta))},
                          rationale=f"空调温度{'上调' if action=='up' else '下调'} 1℃")]
        return [_tool("control_ac", {"location": location, "action": "on"},
                      rationale="默认开启空调")]

    if intent == IntentName.DEVICE_CURTAIN.value:
        ac = "open" if action in ("on", None) else "close"
        return [_tool("control_curtain", {"location": location, "action": ac},
                      rationale=f"窗帘 {ac}")]

    if intent == IntentName.DEVICE_TV.value:
        return [_tool("control_tv", {"location": location, "action": action or "on"},
                      rationale="电视开关")]

    if intent == IntentName.DEVICE_SPEAKER.value:
        return [_tool("play_music", {"location": location,
                                      "action": "play" if action != "off" else "stop"},
                      rationale="音响播放")]

    if intent == IntentName.DEVICE_LOCK.value:
        return [_tool("control_door_lock", {"action": "unlock" if action == "on" else "lock"},
                      rationale="门锁操作（中风险）")]

    if intent == IntentName.DEVICE_GAS.value:
        return [_tool("control_gas_valve", {"action": "close" if action != "on" else "open"},
                      rationale="燃气阀操作（高风险）")]

    if intent == IntentName.DEVICE_ROBOT.value:
        return [_tool("control_robot_cleaner", {"action": "start" if action != "off" else "pause"},
                      rationale="扫地机操作")]

    if intent == IntentName.DEVICE_AIR_PURIFIER.value:
        return [_tool("control_air_purifier",
                       {"location": location, "action": "off" if action == "off" else "on",
                        "speed": "auto"},
                       rationale="空气净化器")]

    if intent == IntentName.DEVICE_HUMIDIFIER.value:
        return [_tool("control_humidifier",
                       {"location": location, "action": "off" if action == "off" else "on"},
                       rationale="加湿器")]

    if intent == IntentName.DEVICE_FRESH_AIR.value:
        return [_tool("control_fresh_air",
                       {"location": location, "action": "off" if action == "off" else "on",
                        "level": "mid"},
                       rationale="新风系统")]

    if intent == IntentName.DEVICE_WATER_HEATER.value:
        return [_tool("control_water_heater",
                       {"action": "off" if action == "off" else "on"},
                       rationale="热水器（中风险）")]

    return []


def _plan_security_check(slots: Slots, state: dict, profile: dict) -> list[ToolCall]:
    """安全巡检：调用 security_check 工具汇总状态，并对发现的问题生成处置建议。"""
    return [
        _tool("security_check", {"scope": "all"},
              rationale="对门锁/燃气/窗户/摄像头做一次巡检并汇总报告"),
    ]


def _plan_movie_v2(slots: Slots, state: dict, profile: dict) -> list[ToolCall]:
    return _plan_movie(slots, state, profile)


def _plan_safety_event(intent: str, slots: Slots, state: dict, profile: dict) -> list[ToolCall]:
    """安全事件预案：从'风险拦截'升级到'主动处理危险事件'。"""
    contact = (profile.get("emergency_contacts") or ["爸爸手机"])[0]
    state["emergency_active"] = True

    if intent == IntentName.SAFETY_GAS_LEAK.value:
        return [
            _tool("control_gas_valve", {"action": "close"},
                  rationale="紧急关闭燃气总阀（应急放行）"),
            _tool("control_light", {"location": "全屋", "action": "off"},
                  rationale="关闭所有灯避免明火"),
            _tool("control_tv", {"location": "客厅", "action": "off"},
                  rationale="关闭电器避免火花"),
            _tool("send_reminder",
                  {"to": "全家", "content": "疑似燃气泄漏！请立刻打开门窗通风，避免使用明火与电器开关。", "channel": "both"},
                  rationale="语音+屏幕双通道告警"),
            _tool("emergency_call", {"contact": contact, "reason": "厨房疑似燃气泄漏"},
                  rationale="呼叫紧急联系人"),
        ]
    if intent == IntentName.SAFETY_ELDER_NO_RESP.value:
        return [
            _tool("control_light", {"location": "主卧", "action": "set", "brightness": 80},
                  rationale="提高房间亮度便于查看"),
            _tool("send_reminder",
                  {"to": "老人", "content": "您没事吧？请回应一声，或按下应急按钮。", "channel": "voice"},
                  rationale="语音呼叫确认"),
            _tool("emergency_call", {"contact": contact, "reason": "老人长时间无响应"},
                  rationale="联系家属确认"),
        ]
    if intent == IntentName.SAFETY_CHILD_ALONE.value:
        return [
            _tool("send_reminder",
                  {"to": "孩子", "content": "我会陪着你，遇到事请按一下应急按钮，或告诉我。", "channel": "both"},
                  rationale="安抚提示"),
            _tool("control_door_lock", {"action": "lock"},
                  rationale="自动反锁入户门保障安全（应急放行）"),
            _tool("emergency_call", {"contact": contact, "reason": "孩子独自在家，已切到看护模式"},
                  rationale="通知家长"),
        ]
    if intent == IntentName.SAFETY_DOOR_ANOMALY.value:
        return [
            _tool("control_door_lock", {"action": "lock"},
                  rationale="尝试锁门"),
            _tool("send_reminder",
                  {"to": "全家", "content": "检测到门窗异常状态，请确认是否为家庭成员操作。", "channel": "both"},
                  rationale="发出告警"),
            _tool("emergency_call", {"contact": contact, "reason": "门窗异常状态"},
                  rationale="通知家属"),
        ]
    if intent == IntentName.SAFETY_INTRUSION.value:
        return [
            _tool("control_light", {"location": "全屋", "action": "set", "brightness": 100},
                  rationale="全屋点亮震慑"),
            _tool("play_music", {"location": "客厅", "action": "play", "playlist": "警报音"},
                  rationale="播放警报"),
            _tool("emergency_call", {"contact": contact, "reason": "夜间检测到陌生人开门"},
                  rationale="紧急联系家属"),
        ]
    return []


def _plan_care(intent: str, slots: Slots, state: dict, profile: dict) -> list[ToolCall]:
    if intent == IntentName.CARE_FALL.value:
        # 紧急场景：激活 emergency 标志，跳过中风险确认
        state["emergency_active"] = True
        contact = (profile.get("emergency_contacts") or ["爸爸手机"])[0]
        return [
            _tool("control_light", {"location": "全屋", "action": "set", "brightness": 100},
                  rationale="紧急照明：全屋灯调至最亮"),
            _tool("emergency_call", {"contact": contact, "reason": "检测到家庭成员摔倒"},
                  rationale="呼叫紧急联系人"),
            _tool("control_tv", {"location": "客厅", "action": "off"},
                  rationale="关闭娱乐设备避免干扰"),
            _tool("play_music", {"location": "客厅", "action": "stop"},
                  rationale="停止音乐"),
            _tool("control_door_lock", {"action": "unlock"},
                  rationale="解锁入户门方便救援人员进入"),
        ]
    if intent == IntentName.CARE_MEDICINE.value:
        member = slots.member or "奶奶"
        return [_tool("send_reminder", {"to": member,
                                         "content": "该服药了，请按时服用",
                                         "channel": "both"},
                      rationale="向老人提醒服药")]
    if intent == IntentName.CARE_STUDY.value:
        member = slots.member or "小明"
        return [_tool("send_reminder", {"to": member,
                                         "content": "请检查作业完成情况，需要帮助请呼叫家长",
                                         "channel": "screen"},
                      rationale="检查孩子学习")]
    if intent == IntentName.CARE_NIGHT.value:
        return [
            _tool("control_light", {"location": "主卧", "action": "set", "brightness": 10},
                  rationale="开启起夜小灯"),
            _tool("play_music", {"location": "主卧", "action": "play",
                                  "playlist": "白噪音"},
                  rationale="夜间陪伴白噪音"),
        ]
    if intent == IntentName.CARE_WATER.value:
        member = slots.member or "奶奶"
        return [_tool("send_reminder",
                       {"to": member, "content": "记得按时喝水，每两小时一杯水。",
                        "channel": "voice"},
                       rationale="喝水提醒")]
    if intent == IntentName.CARE_EYE_BREAK.value:
        return [_tool("send_reminder",
                       {"to": "小明",
                        "content": "学习半小时啦，请放下书本看远处 5 分钟，让眼睛休息一下。",
                        "channel": "screen"},
                       rationale="护眼休息提醒")]
    if intent == IntentName.CARE_GENERAL_ELDER.value:
        member = slots.member or "奶奶"
        return [
            _tool("send_reminder",
                   {"to": member, "content": "已为您开启关怀模式，房间温度、起夜照明、用药都会照看。",
                    "channel": "voice"},
                   rationale="老人关怀模式总入口"),
            _tool("control_ac", {"location": "主卧", "action": "set_temp",
                                   "temperature": 25, "mode": "auto"},
                   rationale="老人房保持适宜温度 25℃"),
            _tool("control_light", {"location": "主卧", "action": "set", "brightness": 30},
                   rationale="柔和照明，避免起夜摸黑"),
        ]
    return []


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def plan(intent: Intent, slots: Slots, home_state: dict, user_profile: dict,
         now: Optional[datetime] = None) -> list[PlanStep]:
    name = intent.name
    calls: list[ToolCall] = []

    if name == IntentName.MODE_SLEEP.value:
        calls = _plan_sleep(slots, home_state, user_profile)
    elif name == IntentName.MODE_LEAVE.value:
        calls = _plan_leave(slots, home_state, user_profile)
    elif name == IntentName.MODE_HOME.value:
        calls = _plan_home(slots, home_state, user_profile)
    elif name == IntentName.MODE_ENERGY.value:
        calls = _plan_energy(slots, home_state, user_profile)
    elif name == IntentName.MODE_PARTY.value:
        calls = _plan_party(slots, home_state, user_profile)
    elif name == IntentName.MODE_MOVIE.value:
        calls = _plan_movie(slots, home_state, user_profile)
    elif name == IntentName.MODE_STUDY.value:
        calls = _plan_study(slots, home_state, user_profile)
    elif name == IntentName.QUERY_SECURITY_CHECK.value:
        calls = _plan_security_check(slots, home_state, user_profile)
    elif name.startswith("device."):
        calls = _plan_device(name, slots, home_state, user_profile)
    elif name.startswith("care."):
        calls = _plan_care(name, slots, home_state, user_profile)
    elif name.startswith("safety."):
        calls = _plan_safety_event(name, slots, home_state, user_profile)
    elif name == IntentName.QUERY_STATUS.value:
        calls = []  # 查询走 reply 文本，不调工具
    else:
        calls = []

    # 排除条件：根据 slots.extras["exclude_tools"] 过滤掉用户明确拒绝的工具
    exclude_tools = set((slots.extras or {}).get("exclude_tools", []))
    if exclude_tools:
        calls = [c for c in calls if c.name not in exclude_tools]

    # 数值边界校验：温度 / 亮度越界时把动作转为澄清提示
    sanitized: list[ToolCall] = []
    rejections: list[str] = []
    for c in calls:
        if c.name == "control_ac" and c.arguments.get("temperature") is not None:
            ok, msg = validate_temp(float(c.arguments["temperature"]))
            if not ok:
                rejections.append(msg)
                continue
        if c.name == "control_light" and c.arguments.get("brightness") is not None:
            ok, msg = validate_brightness(float(c.arguments["brightness"]))
            if not ok:
                rejections.append(msg)
                continue
        sanitized.append(c)
    calls = sanitized

    steps = []
    for i, c in enumerate(calls, start=1):
        steps.append(PlanStep(step_id=i, description=c.rationale or c.name, tool_call=c))

    # 把 rejections 透传给 main.py 通过 home_state 临时区
    if rejections:
        home_state.setdefault("_validation_warnings", []).extend(rejections)
    return steps
