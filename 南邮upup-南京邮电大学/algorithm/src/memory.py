"""本地记忆模块：基于 SQLite 的家庭偏好/对话历史/设备清单存储。

设计要点：
- 全部存于本地 db 文件，零云端上传，符合"敏感数据本地处理"约束；
- 提供 session 级状态（多轮对话上下文）和持久级状态（家庭偏好、设备清单）；
- 内存占用极小，纯标准库，无需额外依赖。
"""
from __future__ import annotations
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

_DB_PATH = Path(__file__).resolve().parent.parent / "data_local" / "memory.db"


def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS kv (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dialog (
            session_id TEXT,
            turn INTEGER,
            role TEXT,
            content TEXT,
            created_at REAL,
            PRIMARY KEY (session_id, turn)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS preference (
            owner TEXT,
            key TEXT,
            value TEXT,
            updated_at REAL,
            PRIMARY KEY (owner, key)
        )
    """)
    return conn


def kv_set(key: str, value: Any) -> None:
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO kv VALUES (?,?,?)",
                  (key, json.dumps(value, ensure_ascii=False), time.time()))


def kv_get(key: str, default: Any = None) -> Any:
    with _conn() as c:
        row = c.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row[0])
    except json.JSONDecodeError:
        return default


def append_dialog(session_id: str, role: str, content: str) -> int:
    conn = _conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT COALESCE(MAX(turn), -1) FROM dialog WHERE session_id=?",
            (session_id,)).fetchone()
        next_turn = (row[0] if row[0] is not None else -1) + 1
        conn.execute("INSERT INTO dialog VALUES (?,?,?,?,?)",
                     (session_id, next_turn, role, content, time.time()))
        conn.commit()
        return next_turn
    finally:
        conn.close()


def get_dialog(session_id: str, max_turns: int = 8) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT turn, role, content FROM dialog WHERE session_id=? "
            "ORDER BY turn DESC LIMIT ?", (session_id, max_turns)).fetchall()
    rows.reverse()
    return [{"turn": r[0], "role": r[1], "content": r[2]} for r in rows]


def set_preference(owner: str, key: str, value: Any) -> None:
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO preference VALUES (?,?,?,?)",
                  (owner, key, json.dumps(value, ensure_ascii=False), time.time()))


def get_preference(owner: str, key: str, default: Any = None) -> Any:
    with _conn() as c:
        row = c.execute("SELECT value FROM preference WHERE owner=? AND key=?",
                        (owner, key)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row[0])
    except json.JSONDecodeError:
        return default


def get_all_preferences(owner: str) -> dict:
    with _conn() as c:
        rows = c.execute("SELECT key, value FROM preference WHERE owner=?",
                         (owner,)).fetchall()
    out = {}
    for k, v in rows:
        try:
            out[k] = json.loads(v)
        except json.JSONDecodeError:
            out[k] = v
    return out


def new_session_id() -> str:
    return uuid.uuid4().hex[:12]


# 默认家庭画像与状态（首次运行时初始化）
_DEFAULT_HOME_STATE = {
    "rooms": {
        "客厅": {"devices": {
            "light": {"power": "off", "brightness": 0},
            "ac": {"power": "off", "temp": 26, "mode": "auto"},
            "curtain": {"status": "opened"},
            "tv": {"power": "off"},
            "speaker": {"power": "off"},
        }},
        "主卧": {"devices": {
            "light": {"power": "off", "brightness": 0},
            "ac": {"power": "off", "temp": 26, "mode": "auto"},
            "curtain": {"status": "opened"},
        }},
        "次卧": {"devices": {
            "light": {"power": "off", "brightness": 0},
            "ac": {"power": "off", "temp": 26, "mode": "auto"},
        }},
        "厨房": {"devices": {"light": {"power": "off", "brightness": 0}}},
        "儿童房": {"devices": {
            "light": {"power": "off", "brightness": 0},
            "ac": {"power": "off", "temp": 26, "mode": "auto"},
        }},
    },
    "door_lock": {"status": "locked"},
    "gas_valve": {"status": "open"},
    "robot_cleaner": {"status": "dock"},
    "emergency_active": False,
    "reminder_log": [],
    "call_log": [],
}

_DEFAULT_USER_PROFILE = {
    "members": [
        {"name": "爷爷", "role": "elder", "tags": ["高血压", "晨练"]},
        {"name": "奶奶", "role": "elder", "tags": ["糖尿病", "降压药"]},
        {"name": "爸爸", "role": "adult"},
        {"name": "妈妈", "role": "adult"},
        {"name": "小明", "role": "child", "tags": ["小学三年级"]},
    ],
    "preferences": {
        "sleep_temp": 25.0,
        "wake_temp": 24.0,
        "preferred_light_brightness_night": 15,
        "music_genre": "轻音乐",
    },
    "emergency_contacts": ["爸爸手机", "120"],
}


def ensure_defaults() -> tuple[dict, dict]:
    """首次启动时把默认家庭状态/画像写入本地 DB。"""
    state = kv_get("home_state")
    if state is None:
        kv_set("home_state", _DEFAULT_HOME_STATE)
        state = _DEFAULT_HOME_STATE
    profile = kv_get("user_profile")
    if profile is None:
        kv_set("user_profile", _DEFAULT_USER_PROFILE)
        profile = _DEFAULT_USER_PROFILE
    return state, profile


def reset_all() -> None:
    """清空本地数据，回到出厂默认。"""
    if _DB_PATH.exists():
        _DB_PATH.unlink()
