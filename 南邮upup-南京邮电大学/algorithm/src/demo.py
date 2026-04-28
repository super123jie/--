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
}

CN_NAMES = {
    "light": "灯", "ac": "空调", "curtain": "窗帘",
    "tv": "电视", "speaker": "音响", "lock": "门锁",
    "robot_cleaner": "扫地机", "gas_valve": "燃气阀",
}


def _device_tile_html(name: str, info: dict) -> str:
    icon = ICONS.get(name, "•")
    cn = CN_NAMES.get(name, name)
    on = info.get("power") == "on" or info.get("status") in ("opened", "unlocked", "start")
    klass = "on" if on else "off"
    if name == "ac":
        meta = f"{info.get('temp', '-') }℃ · {info.get('mode', 'auto')}"
    elif name == "light":
        meta = f"{info.get('brightness', 0)}%"
    elif name == "curtain":
        meta = info.get("status", "-")
    elif name == "tv":
        meta = "ON" if on else "OFF"
    elif name == "speaker":
        meta = info.get("playlist", "—")
    else:
        meta = json.dumps(info, ensure_ascii=False)[:30]
    return (f"<div class='device-tile {klass}'>"
            f"<span class='device-name'>{icon} {cn}</span>"
            f"<span class='device-meta'>{meta}</span></div>")


def _render_state(state: dict):
    cols = st.columns(3)
    rooms = list(state.get("rooms", {}).items())
    for i, (room, info) in enumerate(rooms):
        with cols[i % 3]:
            tiles = "".join(_device_tile_html(n, d) for n, d in info.get("devices", {}).items())
            st.markdown(
                f"<div class='card'><h4>🏠 {room}</h4>{tiles}</div>",
                unsafe_allow_html=True)
    # 全屋安全设备
    door = state.get("door_lock", {}).get("status", "-")
    gas = state.get("gas_valve", {}).get("status", "-")
    robot = state.get("robot_cleaner", {}).get("status", "-")
    st.markdown(
        f"""<div class='card'><h4>🛡️ 全屋安全</h4>
        <span class='metric-pill'>🔐 入户门: {door}</span>
        <span class='metric-pill'>🔥 燃气阀: {gas}</span>
        <span class='metric-pill'>🤖 扫地机: {robot}</span>
        </div>""", unsafe_allow_html=True)


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
        "🎉 聚会": "聚会模式",
        "🔋 节能": "启动节能模式",
        "🧓 老人摔倒": "奶奶摔倒了！",
        "💊 提醒吃药": "提醒爷爷吃降压药",
        "📚 检查作业": "看看小明写作业了吗",
        "🔥 煤气泄漏": "厨房闻到煤气味了",
        "👶 孩子独自": "孩子一个人在家",
    }
    for label, text in quick.items():
        if st.button(label, use_container_width=True, key=f"q_{label}"):
            st.session_state.pending_input = text

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
