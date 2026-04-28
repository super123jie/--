"""复合指令拆解：把"打开厨房灯和客厅空调到26度"拆成多个子任务。

策略：
1. 用连接词（和/以及/还有/再/同时/并/再把/顺便）切句；
2. 每个子句单独走意图+槽位+规划；
3. 上层把多个子规划串接为一个统一计划。

仅当原句确实含连接词且切完后每一段都含设备/动作槽位时才视为复合句，
否则返回 [原文]，避免误切单意图复合句（如"我想要睡觉了"）。
"""
from __future__ import annotations
import re
from typing import List

# 连接词模式：保留分隔符以便计数
_SPLIT_PATTERN = re.compile(r"\s*(?:，|,|；|;|和|以及|还有|再把|顺便|同时|并把|再|顺道)\s*")

# 简易设备/动作关键词（命中说明子句具备执行可能）
_DEVICE_KEYWORDS = {
    "灯", "灯光", "空调", "窗帘", "电视", "音响", "音箱",
    "门锁", "燃气", "扫地机", "热水器", "新风", "音乐",
}
_ACTION_KEYWORDS = {
    "开", "关", "打开", "关闭", "调", "升", "降", "拉", "锁",
    "解锁", "播放", "停止", "暂停", "启动",
}


def _looks_actionable(sub: str) -> bool:
    return (any(k in sub for k in _DEVICE_KEYWORDS) or
            any(k in sub for k in _ACTION_KEYWORDS))


def split_compound(text: str) -> List[str]:
    """把复合句切成多个可独立执行的子句。

    返回的列表保证元素 ≥ 1。仅在确实存在多个 actionable 子句时才返回多个，
    否则返回原文一项以避免误切。
    """
    text = text.strip()
    if not text:
        return [text]

    parts = [p.strip() for p in _SPLIT_PATTERN.split(text) if p.strip()]
    if len(parts) <= 1:
        return [text]

    # 至少有 2 段都 actionable，才认为是真正的复合句
    actionable = [p for p in parts if _looks_actionable(p)]
    if len(actionable) < 2:
        return [text]

    # 把不带设备的 fragment 合并到最近的 actionable 段（简化处理）
    out: List[str] = []
    buf = ""
    for p in parts:
        if _looks_actionable(p):
            if buf:
                p = buf + " " + p
                buf = ""
            out.append(p)
        else:
            buf = (buf + " " + p).strip() if buf else p
    if buf and out:
        out[-1] = out[-1] + " " + buf
    elif buf:
        out.append(buf)
    return out if out else [text]


# 否定 / 排除条件解析 ------------------------------------------------------

_EXCLUDE_PATTERN = re.compile(
    r"(?:别|不要|不用|不让|跳过|排除|除了|除外)\s*"
    r"(开|关|打开|关闭|锁|解锁|拉|启动|停止|播放|"
    r"灯|灯光|空调|窗帘|电视|音响|音箱|门|门锁|燃气|"
    r"煤气|扫地机|热水器|新风|音乐)"
)

_TOOL_KEYWORDS = {
    "门": "control_door_lock", "门锁": "control_door_lock",
    "锁": "control_door_lock", "解锁": "control_door_lock",
    "燃气": "control_gas_valve", "煤气": "control_gas_valve",
    "电视": "control_tv",
    "灯": "control_light", "灯光": "control_light",
    "空调": "control_ac",
    "窗帘": "control_curtain",
    "音响": "play_music", "音箱": "play_music", "音乐": "play_music",
    "扫地机": "control_robot_cleaner",
}


def parse_exclusions(text: str) -> dict:
    """解析否定/排除约束。

    返回 {"exclude_tools": [...], "exclude_keywords": [...]}。
    例如"睡觉模式但别锁门" → exclude_tools=["control_door_lock"]
    """
    excludes_kw = set()
    excludes_tools = set()
    for m in _EXCLUDE_PATTERN.finditer(text):
        kw = m.group(1)
        excludes_kw.add(kw)
        tool = _TOOL_KEYWORDS.get(kw)
        if tool:
            excludes_tools.add(tool)
    return {
        "exclude_tools": sorted(excludes_tools),
        "exclude_keywords": sorted(excludes_kw),
    }
