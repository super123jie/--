"""Streamlit Web Demo：HomeCare-Agent 智能家居交互界面 V4。

特性：
- 深色科技风 UI + 渐变 + 玻璃拟态卡片；
- 浏览器语音输入（streamlit_mic_recorder Web Speech API，离线/在线均可）；
- 设备状态图标网格、风险颜色分级、阶段耗时柱状图；
- 快捷场景按钮、实时回复气泡、历史多轮对话。
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from main import run  # noqa: E402
from src.memory import new_session_id, ensure_defaults, reset_all  # noqa: E402
from src import llm as _llm  # noqa: E402
from src.floorplan_layout import HOTSPOTS, COLOR_MAP, resolve_hotspot_state  # noqa: E402

import base64

try:
    from streamlit_mic_recorder import speech_to_text
    _HAS_MIC = True
except Exception:
    _HAS_MIC = False


# ---------------------------------------------------------------------------
# 页面配置 + 自定义 CSS
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="HomeCare-Agent · 兴享智家",
    layout="wide",
    page_icon="🏠",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
:root{
    --primary:#7c5cff;
    --primary-soft:#a48bff;
    --bg-0:#0f1226;
    --bg-1:#1a1d3a;
    --bg-2:#252a52;
    --txt:#e6e8ff;
    --muted:#a4a8c8;
    --ok:#3ddc97;
    --warn:#ffb84d;
    --danger:#ff5e8a;
}
html, body, [data-testid="stAppViewContainer"]{
    background:
      radial-gradient(1200px 600px at 10% -20%, rgba(124,92,255,.18), transparent 60%),
      radial-gradient(1000px 700px at 110% 10%, rgba(61,220,151,.10), transparent 50%),
      var(--bg-0) !important;
    color: var(--txt);
}
.block-container{ padding-top: 1.2rem; }
[data-testid="stSidebar"]{
    background: linear-gradient(180deg, #141633 0%, #0f1226 100%);
    border-right: 1px solid rgba(255,255,255,.05);
}
[data-testid="stSidebar"] .stButton>button{
    border-radius: 12px;
    background: rgba(255,255,255,.04);
    border: 1px solid rgba(255,255,255,.08);
    color: var(--txt);
    padding: .55rem .9rem;
    transition: all .2s;
}
[data-testid="stSidebar"] .stButton>button:hover{
    background: rgba(124,92,255,.18);
    border-color: var(--primary);
    transform: translateX(2px);
}
.hero{
    padding: 1.2rem 1.6rem;
    border-radius: 18px;
    background: linear-gradient(135deg, rgba(124,92,255,.18), rgba(61,220,151,.08));
    border: 1px solid rgba(124,92,255,.28);
    margin-bottom: 1.2rem;
}
.hero h1{
    font-size: 1.8rem;
    font-weight: 700;
    margin: 0;
    background: linear-gradient(90deg, #fff, #c7c0ff 60%, #8be9c4);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}
.hero p{
    margin: .25rem 0 0; color: var(--muted); font-size: .92rem;
}
.tag{
    display:inline-block; padding:2px 10px; border-radius: 999px;
    font-size:.72rem; margin-right:6px;
    background: rgba(124,92,255,.15); border:1px solid rgba(124,92,255,.4);
    color: var(--primary-soft);
}
.tag.ok{ background: rgba(61,220,151,.12); border-color:#3ddc97; color:#3ddc97; }
.tag.warn{ background: rgba(255,184,77,.12); border-color:#ffb84d; color:#ffb84d; }
.tag.danger{ background: rgba(255,94,138,.12); border-color:#ff5e8a; color:#ff5e8a; }

.card{
    padding: 1rem 1.2rem; border-radius: 14px;
    background: rgba(255,255,255,.03);
    border: 1px solid rgba(255,255,255,.06);
    backdrop-filter: blur(6px);
    margin-bottom: .8rem;
}
.card h4{ margin:0 0 .55rem 0; font-size: .98rem; color: var(--primary-soft); font-weight:600;}

.bubble-user{
    background: linear-gradient(135deg, #4f3df0 0%, #7c5cff 100%);
    color: #fff;
    padding: .8rem 1rem; border-radius: 18px 18px 4px 18px;
    margin-bottom: .5rem;
    box-shadow: 0 4px 18px rgba(124,92,255,.35);
}
.bubble-agent{
    background: rgba(255,255,255,.05);
    border:1px solid rgba(255,255,255,.08);
    color: var(--txt);
    padding: .8rem 1rem; border-radius: 18px 18px 18px 4px;
    margin-bottom: .9rem;
}
.bubble-warn{
    background: linear-gradient(135deg, rgba(255,184,77,.15), rgba(255,94,138,.10));
    border-left: 3px solid #ffb84d;
    color: var(--txt);
    padding: .8rem 1rem; border-radius: 4px 14px 14px 4px;
    margin-bottom: .9rem;
}

.device-tile{
    padding: .65rem .8rem; border-radius: 12px;
    background: rgba(255,255,255,.03);
    border: 1px solid rgba(255,255,255,.06);
    margin-bottom: .4rem;
    display:flex; align-items:center; justify-content:space-between;
}
.device-tile.on{ border-color: rgba(61,220,151,.4); background: rgba(61,220,151,.06);}
.device-tile.off{ opacity:.65;}
.device-name{ font-size:.88rem; font-weight:600;}
.device-meta{ font-size:.78rem; color: var(--muted);}

.metric-pill{
    display:inline-block; margin-right:.5rem;
    padding: .35rem .8rem; border-radius:999px;
    background: rgba(124,92,255,.10);
    border:1px solid rgba(124,92,255,.3);
    color: var(--primary-soft);
    font-size: .82rem; font-weight: 600;
}

[data-testid="stTextInput"] input{
    background: rgba(255,255,255,.04) !important;
    border-radius: 12px !important;
    border: 1px solid rgba(255,255,255,.10) !important;
    color: var(--txt) !important;
    font-size: 1rem !important;
}
[data-testid="stTextInput"] input:focus{
    border-color: var(--primary) !important;
    box-shadow: 0 0 0 3px rgba(124,92,255,.25);
}

.stButton>button[kind="primary"]{
    background: linear-gradient(135deg, #7c5cff, #4f3df0);
    border: none;
    border-radius: 12px;
    box-shadow: 0 6px 20px rgba(124,92,255,.45);
    transition: transform .15s;
}
.stButton>button[kind="primary"]:hover{ transform: translateY(-1px); }

div[data-testid="stExpander"]{
    border-radius: 12px;
    border: 1px solid rgba(255,255,255,.06);
    background: rgba(255,255,255,.02);
}

.empty-state{
    text-align:center; padding: 2rem 1rem; color: var(--muted);
    border: 1px dashed rgba(255,255,255,.12); border-radius: 16px;
}

.section-title{
    font-size: 1.05rem; font-weight: 700; margin: 1rem 0 .6rem 0;
    display:flex; align-items:center; gap:.5rem;
}
.section-title::before{
    content:""; width: 4px; height: 18px; border-radius: 2px;
    background: linear-gradient(180deg, var(--primary), var(--ok));
}

footer{ visibility: hidden; }

/* ===== 3D 户型图 + 设备热点 ===== */
.floorplan-wrap{
    position: relative;
    width: 100%;
    aspect-ratio: 4 / 3;
    border-radius: 18px;
    overflow: hidden;
    background: rgba(255,255,255,.02);
    border: 1px solid rgba(124,92,255,.30);
    box-shadow: 0 8px 32px rgba(15,18,38,.35),
                inset 0 0 60px rgba(124,92,255,.06);
    margin-bottom: 1rem;
}
.floorplan-bg{
    position: absolute; inset: 0;
    width: 100%; height: 100%;
    object-fit: cover;
    opacity: .72;
    filter: saturate(.85) brightness(.92);
    pointer-events: none;
    user-select: none;
}
.floorplan-overlay{
    position: absolute; inset: 0;
    background: linear-gradient(135deg, rgba(15,18,38,.10), rgba(124,92,255,.06));
    pointer-events: none;
}
.hotspot{
    position: absolute;
    width: 38px; height: 38px;
    transform: translate(-50%, -50%);
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 18px;
    background: rgba(20,22,50,.55);
    border: 1.5px solid rgba(180,200,230,.30);
    box-shadow: 0 2px 8px rgba(0,0,0,.35);
    transition: all .35s cubic-bezier(.4,0,.2,1);
    backdrop-filter: blur(4px);
    cursor: default;
    z-index: 5;
}
.hotspot.on{
    background: var(--glow-bg, rgba(255,200,100,.35));
    border-color: var(--glow-color, rgba(255,200,100,.95));
    box-shadow: 0 0 18px var(--glow-color, rgba(255,200,100,.85)),
                0 0 36px var(--glow-color, rgba(255,200,100,.45)),
                0 0 60px var(--glow-color, rgba(255,200,100,.20));
    transform: translate(-50%, -50%) scale(1.18);
    animation: pulse 2.4s ease-in-out infinite;
}
@keyframes pulse{
    0%, 100% { transform: translate(-50%, -50%) scale(1.18); }
    50%      { transform: translate(-50%, -50%) scale(1.30); }
}
.hotspot-label{
    position: absolute; top: 110%; left: 50%;
    transform: translateX(-50%);
    font-size: 11px;
    font-weight: 600;
    white-space: nowrap;
    background: rgba(15,18,38,.92);
    padding: 3px 8px;
    border-radius: 6px;
    color: var(--muted);
    pointer-events: none;
    box-shadow: 0 2px 6px rgba(0,0,0,.4);
    letter-spacing: .5px;
}
.hotspot.on .hotspot-label{
    color: var(--glow-color);
    border: 1px solid var(--glow-color);
    background: rgba(15,18,38,.96);
}
.floorplan-legend{
    position: absolute;
    right: 12px; top: 12px;
    background: rgba(15,18,38,.78);
    border: 1px solid rgba(255,255,255,.10);
    border-radius: 10px;
    padding: 8px 12px;
    font-size: 11px;
    color: var(--muted);
    backdrop-filter: blur(8px);
    pointer-events: none;
    z-index: 6;
}
.floorplan-legend b{ color: var(--primary-soft); display: block; margin-bottom: 4px; font-size: 12px;}
.floorplan-legend span{ display: inline-block; margin-right: 8px;}

/* 紧凑版下方状态条 */
.compact-room{
    padding: .7rem .9rem;
    border-radius: 12px;
    background: rgba(255,255,255,.03);
    border: 1px solid rgba(255,255,255,.06);
    margin-bottom: .55rem;
}
.compact-room h5{
    margin: 0 0 .4rem 0;
    font-size: .92rem;
    color: var(--primary-soft);
}
.compact-room .chip{
    display: inline-block;
    margin: 2px 6px 2px 0;
    padding: 3px 9px;
    border-radius: 999px;
    font-size: .76rem;
    background: rgba(255,255,255,.04);
    border: 1px solid rgba(255,255,255,.08);
    color: var(--muted);
}
.compact-room .chip.on{
    background: rgba(61,220,151,.10);
    border-color: rgba(61,220,151,.45);
    color: var(--ok);
}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 设备图标 + 渲染辅助
# ---------------------------------------------------------------------------
ICONS = {
    "light": "💡", "ac": "❄️", "curtain": "🪟",
    "tv": "📺", "speaker": "🔊", "lock": "🔐",
    "robot_cleaner": "🤖", "gas_valve": "🔥",
    "air_purifier": "🌬️", "humidifier": "💧",
    "fresh_air": "🌀", "water_heater": "♨️",
}

CN_NAMES = {
    "light": "灯", "ac": "空调", "curtain": "窗帘",
    "tv": "电视", "speaker": "音响", "lock": "门锁",
    "robot_cleaner": "扫地机", "gas_valve": "燃气阀",
    "air_purifier": "空气净化器", "humidifier": "加湿器",
    "fresh_air": "新风", "water_heater": "热水器",
}


def _device_tile_html(name: str, info: dict) -> str:
    icon = ICONS.get(name, "•")
    cn = CN_NAMES.get(name, name)
    on = info.get("power") == "on" or info.get("status") in ("opened", "unlocked", "start")
    klass = "on" if on else "off"
    if name == "ac":
        meta = f"{info.get('temp', '-')}℃ · {info.get('mode', 'auto')}"
    elif name == "light":
        meta = f"{info.get('brightness', 0)}%"
    elif name == "curtain":
        meta = info.get("status", "-")
    elif name == "tv":
        meta = "ON" if on else "OFF"
    elif name == "speaker":
        playlist = info.get("playlist") or ""
        meta = (playlist if (on and playlist) else ("ON" if on else "OFF"))
    elif name == "air_purifier":
        meta = f"{'ON' if on else 'OFF'} · {info.get('speed', 'auto')}"
    elif name == "humidifier":
        th = info.get("target_humidity")
        meta = f"{'ON' if on else 'OFF'}" + (f" · 目标 {th}%" if th is not None else "")
    elif name == "fresh_air":
        meta = f"{'ON' if on else 'OFF'} · {info.get('level', 'mid')}档"
    elif name == "water_heater":
        t = info.get("temperature")
        meta = f"{'ON' if on else 'OFF'}" + (f" · {t}℃" if t is not None else "")
    else:
        # 兜底：仅显示开关状态，避免把整个 dict 撕碎到 UI 上
        meta = "ON" if on else "OFF"
    return (f"<div class='device-tile {klass}'>"
            f"<span class='device-name'>{icon} {cn}</span>"
            f"<span class='device-meta'>{meta}</span></div>")


@st.cache_data(show_spinner=False)
def _bg_b64() -> str:
    """加载背景户型图为 base64 内嵌（避开 Streamlit 静态目录限制）。"""
    p = _ROOT / "static" / "bg_floorplan.png"
    if not p.exists():
        return ""
    return base64.b64encode(p.read_bytes()).decode("ascii")


def _render_state(state: dict):
    """3D 户型图 + 设备热点联动版状态渲染。"""
    bg = _bg_b64()
    spots_html: list[str] = []

    for key, pos in HOTSPOTS.items():
        on, label = resolve_hotspot_state(key, state)
        glow_color = COLOR_MAP[pos["color"]] if on else COLOR_MAP["off"]
        glow_bg = glow_color.replace("0.85", "0.30").replace("0.90", "0.30") \
                              .replace("0.80", "0.25").replace("0.70", "0.25")
        klass = "hotspot on" if on else "hotspot"
        spots_html.append(
            f'<div class="{klass}" '
            f'style="left:{pos["x"]}%;top:{pos["y"]}%;'
            f'--glow-color:{glow_color};--glow-bg:{glow_bg};">'
            f'{pos["icon"]}'
            f'<span class="hotspot-label">{pos["label_zh"]} · {label}</span>'
            f'</div>'
        )

    legend_html = (
        '<div class="floorplan-legend">'
        '<b>设备状态</b>'
        '<span>🟡 灯</span><span>🔵 空调</span><span>🟣 音响</span>'
        '<span>🔐 门锁</span><span>🔥 燃气</span>'
        '</div>'
    )

    bg_img = (f'<img class="floorplan-bg" src="data:image/png;base64,{bg}" />'
               if bg else
               '<div class="floorplan-bg" style="background:linear-gradient(135deg,#1a1d3a,#252a52);"></div>')

    st.markdown(
        f'<div class="floorplan-wrap">'
        f'{bg_img}'
        f'<div class="floorplan-overlay"></div>'
        f'{legend_html}'
        f'{"".join(spots_html)}'
        f'</div>',
        unsafe_allow_html=True,
    )

    # 紧凑版状态条（每个房间一行）
    _render_state_compact(state)


def _render_state_compact(state: dict):
    """紧凑版每房间状态条，用 chip 列表，避免占用太多垂直空间。"""
    rooms = list(state.get("rooms", {}).items())
    cols = st.columns(min(max(len(rooms), 1), 5))
    for i, (room, info) in enumerate(rooms):
        with cols[i % len(cols)]:
            chips: list[str] = []
            for n, d in info.get("devices", {}).items():
                cn = CN_NAMES.get(n, n)
                icon = ICONS.get(n, "•")
                on = (d.get("power") == "on" or
                      d.get("status") in ("opened", "unlocked", "start"))
                # 取关键值
                if n == "ac" and on:
                    extra = f" {d.get('temp', '-')}℃"
                elif n == "light" and on:
                    extra = f" {d.get('brightness', 0)}%"
                else:
                    extra = ""
                klass = "chip on" if on else "chip"
                chips.append(f"<span class='{klass}'>{icon} {cn}{extra}</span>")
            st.markdown(
                f"<div class='compact-room'><h5>🏠 {room}</h5>{''.join(chips)}</div>",
                unsafe_allow_html=True)

    # 全屋安全单独一行
    door = state.get("door_lock", {}).get("status", "-")
    gas = state.get("gas_valve", {}).get("status", "-")
    robot = state.get("robot_cleaner", {}).get("status", "-")
    door_on = door == "unlocked"
    gas_on = gas == "open"
    robot_on = robot in ("start", "running")
    st.markdown(
        f"<div class='compact-room' style='margin-top:.6rem;'>"
        f"<h5>🛡️ 全屋安全</h5>"
        f"<span class='chip {'on' if door_on else ''}'>🔐 入户门: {door}</span>"
        f"<span class='chip {'on' if gas_on else ''}'>🔥 燃气阀: {gas}</span>"
        f"<span class='chip {'on' if robot_on else ''}'>🤖 扫地机: {robot}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )


def _render_plan(plan: list):
    if not plan:
        st.markdown("<div class='empty-state'>本轮无需调用工具</div>",
                     unsafe_allow_html=True)
        return
    for step in plan:
        tc = step.get("tool_call") or {}
        risk = tc.get("risk_level", "low")
        emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(risk, "⚪")
        klass = {"low": "ok", "medium": "warn", "high": "danger"}.get(risk, "")
        with st.expander(f"步骤 {step['step_id']}  {emoji}  {tc.get('name','')}",
                          expanded=False):
            st.markdown(f"**说明：** {step.get('description','')}")
            st.markdown(f"<span class='tag {klass}'>风险 {risk}</span>",
                         unsafe_allow_html=True)
            st.json(tc.get("arguments", {}))


def _render_safety(safety: list, tool_results: list):
    if not safety:
        st.markdown("<div class='empty-state'>无需安全检查</div>",
                     unsafe_allow_html=True)
        return
    rows = []
    for sf, tr in zip(safety, tool_results):
        risk = sf.get("risk_level")
        emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(risk, "⚪")
        klass = {"low": "ok", "medium": "warn", "high": "danger"}.get(risk, "")
        status = tr.get("status", "?")
        name = tr.get("tool_call", {}).get("name", "")
        rows.append(
            f"<div style='padding:.5rem .7rem; border-radius:8px;"
            f"background:rgba(255,255,255,.03); margin-bottom:.4rem;'>"
            f"{emoji} <b>{name}</b> "
            f"<span class='tag {klass}'>{risk}</span> "
            f"<span class='tag'>{status}</span><br/>"
            f"<span style='color:var(--muted);font-size:.85rem'>{sf.get('reason','')}</span></div>"
        )
    st.markdown("".join(rows), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 初始化 session
# ---------------------------------------------------------------------------
if "sid" not in st.session_state:
    st.session_state.sid = new_session_id()
    st.session_state.history = []
    ensure_defaults()


# ---------------------------------------------------------------------------
# 顶部 Hero
# ---------------------------------------------------------------------------
llm_tag = ("<span class='tag ok'>L3 LLM 已就绪</span>"
            if _llm.is_available()
            else "<span class='tag warn'>L3 LLM 未启用</span>")
mic_tag = ("<span class='tag ok'>🎙️ 语音输入</span>"
            if _HAS_MIC else "<span class='tag warn'>🎙️ 未安装语音模块</span>")

st.markdown(f"""
<div class='hero'>
    <h1>🏠 HomeCare-Agent · 端侧家庭智能体</h1>
    <p>南邮upup · 南京邮电大学 · 中兴捧月「兴享智家」赛道</p>
    <div style='margin-top:.6rem;'>
        <span class='tag'>三层意图识别</span>
        <span class='tag'>Function Calling</span>
        <span class='tag'>本地隐私</span>
        <span class='tag'>多轮上下文</span>
        {llm_tag} {mic_tag}
    </div>
</div>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 侧栏
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🆔 会话")
    st.code(st.session_state.sid, language="text")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔄 新会话", use_container_width=True):
            st.session_state.sid = new_session_id()
            st.session_state.history = []
            st.rerun()
    with c2:
        if st.button("🗑️ 清数据", use_container_width=True):
            reset_all()
            st.session_state.sid = new_session_id()
            st.session_state.history = []
            st.rerun()

    st.markdown("---")
    st.markdown("### ⚡ 快捷场景")
    quick = {
        "🌙 睡觉": "我准备睡觉了，帮我把家里调整一下",
        "🚪 离家": "我要出门了",
        "🏡 回家": "我刚到家",
        "🎬 观影": "我要看电影了，把灯调暗一点",
        "📚 学习": "孩子要写作业了，开启学习模式",
        "🎉 聚会": "聚会模式",
        "🔋 节能": "启动节能模式",
        "🛡️ 安全巡检": "帮我检查家里是否安全",
        "🌬️ 净化器": "打开空气净化器",
        "💧 加湿器": "晚上有点干，打开加湿器",
        "🧓 老人摔倒": "奶奶摔倒了！",
        "💊 提醒吃药": "提醒爷爷吃降压药",
        "🔥 煤气泄漏": "厨房闻到煤气味了",
        "👶 孩子独自": "孩子一个人在家",
    }
    # 快捷按钮：点击直接运行 Agent 并刷新页面，不依赖 text_input value
    # （带 key 的 text_input 会忽略 value 参数，必须直接 rerun）
    for label, text in quick.items():
        if st.button(label, use_container_width=True, key=f"q_{label}"):
            out = run(text, session_id=st.session_state.sid)
            st.session_state.history.append(out)
            st.rerun()

    st.markdown("---")
    st.markdown("### 🔒 端侧 & 隐私")
    if _llm.is_available():
        st.markdown("<span class='tag ok'>✅ L3 LLM 92MB 本地</span>",
                     unsafe_allow_html=True)
    st.markdown("<span class='tag ok'>✅ 数据全本地</span>",
                 unsafe_allow_html=True)
    st.markdown("<span class='tag ok'>✅ 内存 < 1GB</span>",
                 unsafe_allow_html=True)
    st.markdown("<span class='tag ok'>✅ 零云端上传</span>",
                 unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 输入区：文本 + 语音
# ---------------------------------------------------------------------------
st.markdown("<div class='section-title'>💬 与 Agent 对话</div>",
             unsafe_allow_html=True)

input_col, mic_col = st.columns([5, 1])
with input_col:
    typed = st.text_input(
        "对家庭智能体说点什么…",
        value=st.session_state.pop("pending_input", ""),
        placeholder="例如：我准备睡觉了 / 把客厅空调调到 24 度 / 厨房闻到煤气味了",
        label_visibility="collapsed",
        key="text_input_key",
    )
with mic_col:
    voice_text = None
    if _HAS_MIC:
        voice_text = speech_to_text(
            language="zh-CN",
            start_prompt="🎙️ 按住说话",
            stop_prompt="⏹ 停止",
            just_once=True,
            use_container_width=True,
            key="mic",
        )
    else:
        st.caption("语音不可用")

# 优先采用语音输入
input_text = (voice_text or "").strip() or (typed or "").strip()
if voice_text:
    st.info(f"🎙️ 语音识别结果：{voice_text}")

c1, c2, c3 = st.columns([1, 1, 6])
with c1:
    submit = st.button("🚀 提交", type="primary", use_container_width=True)
with c2:
    confirm_btn = st.button("✅ 确认", use_container_width=True)

# 自动提交语音
auto_submit_voice = bool(voice_text)

if confirm_btn:
    out = run("确认", session_id=st.session_state.sid)
    st.session_state.history.append(out)
elif (submit or auto_submit_voice) and input_text:
    out = run(input_text, session_id=st.session_state.sid)
    st.session_state.history.append(out)


# ---------------------------------------------------------------------------
# 主区：回复 + 意图槽位 + 计划 + 安全 + 状态
# ---------------------------------------------------------------------------
if st.session_state.history:
    last = st.session_state.history[-1]

    # 回复气泡
    st.markdown(
        f"<div class='bubble-user'><b>用户：</b>{last['user_input']}</div>",
        unsafe_allow_html=True)
    if last.get("requires_confirmation"):
        st.markdown(
            f"<div class='bubble-warn'><b>Agent ⚠️：</b>{last['reply']}</div>",
            unsafe_allow_html=True)
    else:
        st.markdown(
            f"<div class='bubble-agent'><b>Agent：</b>{last['reply']}</div>",
            unsafe_allow_html=True)

    a, b = st.columns(2)
    with a:
        st.markdown("<div class='section-title'>🎯 意图与槽位</div>",
                     unsafe_allow_html=True)
        intent = last["intent"]
        slots = last["slots"]
        st.markdown(
            f"<div class='card'>"
            f"<span class='tag'>意图: {intent['name']}</span>"
            f"<span class='tag ok'>置信 {intent['confidence']:.2f}</span></div>",
            unsafe_allow_html=True)
        if slots:
            st.json(slots)

        st.markdown("<div class='section-title'>📋 规划步骤</div>",
                     unsafe_allow_html=True)
        _render_plan(last.get("plan", []))

    with b:
        st.markdown("<div class='section-title'>🛡️ 安全裁决</div>",
                     unsafe_allow_html=True)
        _render_safety(last.get("safety", []), last.get("tool_results", []))

        st.markdown("<div class='section-title'>⏱️ 阶段耗时（毫秒）</div>",
                     unsafe_allow_html=True)
        timing = last.get("timing_ms", {})
        if timing:
            total = sum(timing.values())
            st.markdown(
                f"<span class='metric-pill'>总耗时 {total:.1f} ms</span>",
                unsafe_allow_html=True)
            st.bar_chart(timing, height=200)

    st.markdown("<div class='section-title'>🏘️ 当前家庭状态</div>",
                 unsafe_allow_html=True)
    _render_state(last.get("home_state_after", {}))

    st.markdown("<div class='section-title'>🗂️ 历史对话</div>",
                 unsafe_allow_html=True)
    for h in reversed(st.session_state.history[-6:]):
        st.markdown(f"<div class='bubble-user'>{h['user_input']}</div>",
                     unsafe_allow_html=True)
        st.markdown(f"<div class='bubble-agent'>{h['reply']}</div>",
                     unsafe_allow_html=True)
else:
    st.markdown(
        "<div class='empty-state'>👆 在上方输入框输入指令、点击 🎙️ 语音、"
        "或在侧栏选择快捷场景开始体验</div>", unsafe_allow_html=True)
    state, _ = ensure_defaults()
    st.markdown("<div class='section-title'>🏘️ 当前家庭状态（默认）</div>",
                 unsafe_allow_html=True)
    _render_state(state)
