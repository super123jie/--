"""中文数字解析：把"二十六度""十五""半小时""三十分钟"等表达转为阿拉伯数值。

仅覆盖家庭场景常见的数值范围（0-100），保证轻量。
"""
from __future__ import annotations
import re

_DIGITS = {
    "零": 0, "〇": 0, "○": 0,
    "一": 1, "二": 2, "两": 2, "俩": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}
_UNITS = {"十": 10, "百": 100}


def parse_zh_number(text: str) -> int | float | None:
    """解析单个中文数字串。失败返回 None。

    支持：一/二/十/十五/二十六/三十/百/半。
    """
    if not text:
        return None
    text = text.strip()
    if text in ("半",):
        return 0.5
    if text == "几":
        return None
    # 阿拉伯数字直通
    if re.fullmatch(r"\d+(\.\d+)?", text):
        try:
            return float(text) if "." in text else int(text)
        except ValueError:
            return None

    n = 0
    cur = 0
    for ch in text:
        if ch in _UNITS:
            if cur == 0:
                cur = 1
            n += cur * _UNITS[ch]
            cur = 0
        elif ch in _DIGITS:
            cur = _DIGITS[ch]
        else:
            return None
    n += cur
    return n if n > 0 else None


# 中文数字 + 单位 的统一正则
_ZH_NUM_PATTERN = re.compile(
    r"([零〇○一二两俩三四五六七八九十百半]+|\d+(?:\.\d+)?)\s*"
    r"(度|℃|百分|%|分钟|小时|秒|分)?"
)


def find_first_number(text: str) -> tuple[float | None, str | None]:
    """在文本中查找第一个数值（中/阿拉伯），返回 (数值, 单位)。"""
    m = _ZH_NUM_PATTERN.search(text)
    if not m:
        return None, None
    raw, unit = m.group(1), m.group(2)
    val = parse_zh_number(raw)
    return (val, unit) if val is not None else (None, None)
