"""3D 户型图上的设备热点坐标表。

每个热点定义在背景图（algorithm/static/bg_floorplan.png）上的相对坐标
（x、y 单位为相对百分比 0-100，原点左上角），以及发光颜色。

后续可在浏览器里逐个微调（改这个表，刷新页面立刻生效）。
"""
from __future__ import annotations

# (房间名, 设备名) → 热点 / 全屋设备名 → 热点
HOTSPOTS: dict = {
    # 主卧（左上）
    ("主卧", "light"):    {"x": 25, "y": 22, "color": "warm",    "icon": "💡", "label_zh": "主卧灯"},
    ("主卧", "ac"):       {"x": 32, "y": 30, "color": "blue",    "icon": "❄️", "label_zh": "主卧空调"},
    ("主卧", "curtain"):  {"x": 14, "y": 32, "color": "neutral", "icon": "🪟", "label_zh": "主卧窗帘"},

    # 次卧（右上）
    ("次卧", "light"):    {"x": 76, "y": 18, "color": "warm",    "icon": "💡", "label_zh": "次卧灯"},
    ("次卧", "ac"):       {"x": 70, "y": 26, "color": "blue",    "icon": "❄️", "label_zh": "次卧空调"},

    # 儿童房（中右）
    ("儿童房", "light"):  {"x": 56, "y": 38, "color": "warm",    "icon": "💡", "label_zh": "儿童房灯"},
    ("儿童房", "ac"):     {"x": 62, "y": 45, "color": "blue",    "icon": "❄️", "label_zh": "儿童房空调"},

    # 客厅（左中）
    ("客厅", "light"):    {"x": 32, "y": 60, "color": "warm",    "icon": "💡", "label_zh": "客厅灯"},
    ("客厅", "ac"):       {"x": 22, "y": 50, "color": "blue",    "icon": "❄️", "label_zh": "客厅空调"},
    ("客厅", "tv"):       {"x": 40, "y": 56, "color": "cyan",    "icon": "📺", "label_zh": "电视"},
    ("客厅", "curtain"):  {"x": 14, "y": 62, "color": "neutral", "icon": "🪟", "label_zh": "客厅窗帘"},
    ("客厅", "speaker"):  {"x": 42, "y": 65, "color": "purple",  "icon": "🔊", "label_zh": "音响"},

    # 厨房（右）
    ("厨房", "light"):           {"x": 84, "y": 50, "color": "warm",   "icon": "💡", "label_zh": "厨房灯"},
    ("厨房", "air_purifier"):    {"x": 78, "y": 60, "color": "green",  "icon": "🌬️", "label_zh": "净化器"},
    ("厨房", "humidifier"):      {"x": 88, "y": 64, "color": "cyan",   "icon": "💧", "label_zh": "加湿器"},

    # 全屋安全（底部）
    "door_lock":     {"x": 60, "y": 84, "color": "warn",   "icon": "🔐", "label_zh": "入户门"},
    "gas_valve":     {"x": 84, "y": 78, "color": "danger", "icon": "🔥", "label_zh": "燃气阀"},
    "robot_cleaner": {"x": 48, "y": 78, "color": "neutral", "icon": "🤖", "label_zh": "扫地机"},
}


COLOR_MAP: dict[str, str] = {
    "warm":    "rgba(255, 200, 100, 0.85)",    # 暖光（灯）
    "blue":    "rgba(100, 180, 255, 0.85)",    # 冷蓝（空调）
    "cyan":    "rgba(120, 230, 220, 0.85)",    # 青色（电视、加湿）
    "purple":  "rgba(200, 130, 255, 0.85)",    # 紫色（音响）
    "green":   "rgba(100, 220, 150, 0.80)",    # 绿色（净化器）
    "warn":    "rgba(255, 180, 80, 0.85)",     # 黄警示（门锁）
    "danger":  "rgba(255, 100, 130, 0.90)",    # 红警告（燃气阀）
    "neutral": "rgba(180, 200, 230, 0.70)",    # 灰青（窗帘、扫地机）
    "off":     "rgba(160, 165, 200, 0.30)",    # 关闭态（半透明灰）
}


def resolve_hotspot_state(key, state: dict) -> tuple[bool, str]:
    """根据 home_state 推断热点是否激活 + 标签文本。

    返回 (on, label)：
      - light: on/off + 亮度
      - ac: on/off + 温度
      - curtain / door_lock / gas_valve / tv / speaker / robot_cleaner / 净化加湿: 状态文字
    """
    if isinstance(key, tuple):
        room, dev = key
        info = (state.get("rooms", {}).get(room, {}).get("devices", {}) or {}).get(dev, {})
    else:
        info = state.get(key, {})
        dev = key

    if dev == "light":
        on = info.get("power") == "on"
        b = info.get("brightness", 0)
        return on, (f"{b}%" if on else "关")
    if dev == "ac":
        on = info.get("power") == "on"
        t = info.get("temp", "-")
        return on, (f"{t}℃" if on else "关")
    if dev == "curtain":
        opened = info.get("status") == "opened"
        return opened, ("拉开" if opened else "合上")
    if dev == "tv":
        on = info.get("power") == "on"
        return on, ("ON" if on else "OFF")
    if dev == "speaker":
        on = info.get("power") == "on"
        return on, (info.get("playlist") or "ON" if on else "OFF")
    if dev == "air_purifier":
        on = info.get("power") == "on"
        return on, (info.get("speed", "auto") if on else "OFF")
    if dev == "humidifier":
        on = info.get("power") == "on"
        return on, ("加湿中" if on else "OFF")
    if dev == "door_lock":
        unlocked = info.get("status") == "unlocked"
        return unlocked, ("已解锁" if unlocked else "已锁")
    if dev == "gas_valve":
        is_open = info.get("status") == "open"
        return is_open, ("开" if is_open else "关")
    if dev == "robot_cleaner":
        running = info.get("status") in ("start", "running")
        return running, ("工作中" if running else "待机")
    return False, "-"
