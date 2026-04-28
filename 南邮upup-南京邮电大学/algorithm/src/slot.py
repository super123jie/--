"""槽位抽取：jieba 分词 + 词典匹配 + 数值/时间正则 + 中文数字 + 排除条件。

输出结构对齐 schema.Slots。所有数据本地处理，零外部 API。
"""
from __future__ import annotations
import re
from typing import Optional

import jieba

from .schema import Slots
from .zh_num import find_first_number
from .compound import parse_exclusions

# 房间词典
_LOCATION_VOCAB = {
    "客厅": "客厅", "起居室": "客厅",
    "卧室": "卧室", "主卧": "主卧", "次卧": "次卧",
    "厨房": "厨房",
    "卫生间": "卫生间", "洗手间": "卫生间", "浴室": "浴室",
    "书房": "书房",
    "儿童房": "儿童房", "宝宝房": "儿童房",
    "玄关": "玄关",
    "阳台": "阳台",
    "全屋": "全屋", "整个家": "全屋", "家里": "全屋",
}

# 设备词典
_DEVICE_VOCAB = {
    "灯": "light", "灯光": "light", "照明": "light", "台灯": "light",
    "空调": "ac", "AC": "ac",
    "窗帘": "curtain", "帘子": "curtain", "遮光帘": "curtain",
    "电视": "tv", "电视机": "tv",
    "音响": "speaker", "音箱": "speaker",
    "门锁": "lock", "入户门": "lock",
    "燃气": "gas_valve", "煤气": "gas_valve", "燃气阀": "gas_valve",
    "扫地机": "robot_cleaner", "扫地机器人": "robot_cleaner",
    "热水器": "water_heater",
    "新风": "fresh_air", "新风系统": "fresh_air",
}

# 动作词典
_ACTION_VOCAB = {
    "打开": "on", "开": "on", "启动": "on", "开启": "on", "解锁": "on", "开锁": "on",
    "关闭": "off", "关": "off", "关掉": "off", "停止": "off", "上锁": "off", "锁": "off", "锁了": "off", "锁上": "off",
    "调高": "up", "调亮": "up", "升高": "up", "升": "up",
    "调低": "down", "调暗": "down", "降低": "down", "降": "down",
    "拉开": "on", "拉上": "off",
    "暂停": "pause",
}

# 家庭成员词典（运行时可被 user_profile.members 增量覆盖）
_MEMBER_VOCAB_DEFAULT = {
    "爷爷": "爷爷", "奶奶": "奶奶",
    "爸爸": "爸爸", "妈妈": "妈妈",
    "孩子": "孩子", "小孩": "孩子",
    "我": "self", "自己": "self",
}

_NUM_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(度|℃|%|百分|分钟|小时)?")
_TIME_PATTERN = re.compile(
    r"(早上|早晨|上午|中午|下午|傍晚|晚上|夜里|半夜|凌晨|今天|明天|"
    r"\d{1,2}\s*[:：]\s*\d{1,2}|\d+\s*分钟后|\d+\s*小时后)"
)


def _build_member_vocab(user_profile: Optional[dict]) -> dict:
    vocab = dict(_MEMBER_VOCAB_DEFAULT)
    if user_profile and isinstance(user_profile.get("members"), list):
        for m in user_profile["members"]:
            name = m.get("name") if isinstance(m, dict) else m
            if name and isinstance(name, str):
                vocab[name] = name
    return vocab


def extract_slots(text: str, user_profile: Optional[dict] = None) -> Slots:
    """从用户文本抽取槽位。结合分词命中和正则，无需调用模型。"""
    slots = Slots()
    tokens = list(jieba.cut(text))
    member_vocab = _build_member_vocab(user_profile)

    for tok in tokens:
        if slots.location is None and tok in _LOCATION_VOCAB:
            slots.location = _LOCATION_VOCAB[tok]
        if slots.device is None and tok in _DEVICE_VOCAB:
            slots.device = _DEVICE_VOCAB[tok]
        if slots.action is None and tok in _ACTION_VOCAB:
            slots.action = _ACTION_VOCAB[tok]
        if slots.member is None and tok in member_vocab:
            slots.member = member_vocab[tok]

    # 数值：先用中文数字解析（支持"二十六度""十五"），失败再回退到阿拉伯数字
    val, unit = find_first_number(text)
    if val is not None:
        slots.value = float(val)
        if unit:
            slots.extras["value_unit"] = unit
    else:
        m = _NUM_PATTERN.search(text)
        if m:
            try:
                slots.value = float(m.group(1))
                u = m.group(2) or ""
                if u:
                    slots.extras["value_unit"] = u
            except ValueError:
                pass

    # 排除条件解析（"睡觉模式但别锁门"）
    excl = parse_exclusions(text)
    if excl["exclude_tools"]:
        slots.extras["exclude_tools"] = excl["exclude_tools"]
        slots.extras["exclude_keywords"] = excl["exclude_keywords"]

    # 时间表述
    tm = _TIME_PATTERN.search(text)
    if tm:
        slots.time = tm.group(1)

    # 显式动作短语兜底
    if slots.action is None:
        if re.search(r"(开|打开|启动|开启|拉开)", text) and not re.search(r"(不开|别开|不要开)", text):
            slots.action = "on"
        elif re.search(r"(关|关闭|停止|拉上|关掉)", text):
            slots.action = "off"

    # 升降兜底
    if slots.action is None:
        if re.search(r"(高一点|大一点|亮一点|热一点)", text):
            slots.action = "up"
        elif re.search(r"(低一点|小一点|暗一点|冷一点)", text):
            slots.action = "down"

    return slots
