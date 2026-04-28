"""HomeCare-Agent 入口文件。

按官方要求：算法目录下必须存在 main.py，导出 run() 函数。

run(user_input, home_state=None, user_profile=None, session_id=None) -> dict
返回结构化 JSON，可被 Streamlit Demo / 测试脚本 / 任何上层调用方使用。
"""
from __future__ import annotations
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# 让 `python algorithm/main.py` 直接运行时也能 import src/*
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from src.intent import predict_intent
from src.slot import extract_slots
from src.planner import plan
from src.safety import evaluate_all
from src.tools import call_tool
from src.memory import (ensure_defaults, kv_set, append_dialog,
                         get_dialog, new_session_id)
from src.dialog import get_session, merge_slots
from src.schema import (AgentResponse, Intent, Slots, ToolCall, IntentName,
                         RiskLevel)
from src.edge_opt import StageTimer
from src.compound import split_compound

# 能力外关键词：命中即直接走澄清，不继承上轮意图也不调 L3
_OUT_OF_SCOPE = re.compile(
    r"(天气|外卖|股市|股票|新闻|笑话|讲故事|聊天|你叫.*名字|订餐|订票|抢票|"
    r"翻译|下棋|打车|快递|支付|充值|理财|游戏|电影院)"
)


def _build_reply(intent: Intent, plan_steps, safety_verdicts, tool_results,
                 requires_conf: bool, home_state: dict) -> str:
    """生成给用户的自然语言回复。简单模板拼接，离线零依赖。"""
    if intent.name == IntentName.UNKNOWN.value or intent.confidence < 0.4:
        return "抱歉我没太听懂，能换个说法吗？比如：『我准备睡觉了』『把客厅灯打开』。"

    if intent.name == IntentName.QUERY_STATUS.value:
        # 简易状态汇报
        rooms = home_state.get("rooms", {})
        parts = []
        for r, info in rooms.items():
            devs = info.get("devices", {})
            ac = devs.get("ac", {})
            light = devs.get("light", {})
            seg = []
            if ac:
                seg.append(f"空调 {ac.get('power')}({ac.get('temp', '?')}℃)")
            if light:
                seg.append(f"灯 {light.get('power')}({light.get('brightness', 0)}%)")
            if seg:
                parts.append(f"{r}：{'、'.join(seg)}")
        return "当前家居状态：\n" + "\n".join(parts) if parts else "暂无可报告的设备。"

    if requires_conf:
        risky = [tr for tr in tool_results if tr.get("status") == "blocked"]
        names = "、".join(tr["tool_call"]["name"] for tr in risky)
        return (f"识别意图：{intent.name}。已生成 {len(plan_steps)} 步计划，"
                f"其中 {len(risky)} 步涉及风险动作（{names}），请回复『确认』执行，"
                f"或『取消』终止。")

    executed = [tr for tr in tool_results if tr.get("status") == "executed"]
    if not executed:
        return f"已识别意图 {intent.name}，但当前无可执行动作。"
    return f"已为您完成 {len(executed)} 项操作：" + "；".join(
        tr.get("result", {}).get("message", tr["tool_call"]["name"]) for tr in executed)


def _execute_plan(plan_steps, verdicts, home_state, force_execute_high=False):
    """根据 verdicts 执行 plan_steps，返回每步执行状态。"""
    results = []
    for step, v in zip(plan_steps, verdicts):
        tc = step.tool_call
        if tc is None:
            continue
        item = {"step_id": step.step_id, "tool_call": tc.to_dict(),
                "safety": {"allowed": v.allowed, "risk": v.risk_level,
                           "requires_confirmation": v.requires_confirmation,
                           "reason": v.reason}}
        if v.allowed or force_execute_high:
            res = call_tool(tc.name, home_state, **tc.arguments)
            item["status"] = "executed"
            item["result"] = res
        else:
            item["status"] = "blocked"
            item["result"] = {"ok": False, "message": v.reason}
        results.append(item)
    return results


def run(user_input: str = None, home_state: dict = None,
        user_profile: dict = None, session_id: str = None,
        confirm: bool = False) -> dict:
    """对外入口。

    参数：
        user_input: 用户自然语言指令；
        home_state: 当前家庭状态（dict）。None 时从本地 SQLite 加载默认；
        user_profile: 用户/家庭画像（dict）。None 时加载默认；
        session_id: 多轮对话会话 ID；None 时自建；
        confirm: 是否为对待确认计划的确认/取消回复。

    返回：JSON 可序列化 dict，结构见 schema.AgentResponse。
    """
    if not user_input:
        user_input = ""

    timer = StageTimer()

    # --- 0. 状态加载 ---------------------------------------------------
    with timer.stage("load_state"):
        default_state, default_profile = ensure_defaults()
        if home_state is None:
            home_state = default_state
        if user_profile is None:
            user_profile = default_profile
        if not session_id:
            session_id = new_session_id()
        session = get_session(session_id)
        append_dialog(session_id, "user", user_input)

    # --- 1. 处理"确认/取消"快路径 ------------------------------------
    text_strip = user_input.strip()
    if session.pending_plan and text_strip in ("确认", "确定", "好", "好的", "可以", "执行"):
        confirm = True
    if session.pending_plan and text_strip in ("取消", "算了", "不用了", "停"):
        session.pending_plan = []
        kv_set("home_state", home_state)
        return AgentResponse(
            user_input=user_input,
            intent={"name": "dialog.cancel", "confidence": 1.0, "raw": user_input},
            slots={}, plan=[], safety=[], tool_results=[],
            reply="已取消上一步操作。",
            requires_confirmation=False,
            home_state_after=home_state,
            timing_ms=timer.timings,
            session_id=session_id,
        ).to_dict()

    # --- 2. 意图 + 槽位 -----------------------------------------------
    if confirm and session.pending_plan:
        # 复用上一轮的计划，但意图明确标记为 dialog.confirm
        intent = Intent(name="dialog.confirm", confidence=1.0, raw=user_input)
        slots = session.last_slots
        plan_steps = session.pending_plan
    else:
        # 能力外关键词检测：直接拒绝继承，明确返回边界提示
        out_of_scope = bool(_OUT_OF_SCOPE.search(user_input))

        with timer.stage("intent"):
            ctx_intent = None if out_of_scope else session.last_intent
            intent = predict_intent(user_input, last_intent=ctx_intent)
            # 兜底：仅在非能力外、且本轮含明确槽位时继承上轮
            if (not out_of_scope and intent.name == IntentName.UNKNOWN.value
                    and session.last_intent is not None):
                from src.slot import extract_slots as _es
                tmp = _es(user_input, user_profile)
                if (tmp.action or tmp.value is not None or tmp.location or tmp.device):
                    intent = Intent(name=session.last_intent.name,
                                    confidence=max(0.6, session.last_intent.confidence * 0.8),
                                    raw=user_input + " [继承上轮意图]")

        # 复合指令拆解：当意图无法直接覆盖整句（即一句有多个 actionable 子句）时，
        # 把每个子句独立走 intent+slot+plan，串接成统一计划。
        sub_inputs = split_compound(user_input) if not out_of_scope else [user_input]
        compound = len(sub_inputs) > 1
        # 全句的排除约束：先一次性解析整段文本得到 exclude_tools
        from src.compound import parse_exclusions as _pe
        global_excludes = set(_pe(user_input)["exclude_tools"])

        with timer.stage("slot"):
            slots_cur = extract_slots(user_input, user_profile)
            slots = merge_slots(session.last_slots, slots_cur)

        with timer.stage("plan"):
            if compound:
                plan_steps = []
                step_offset = 0
                first_real_intent: Intent | None = None
                for sub in sub_inputs:
                    sub_strip = sub.strip()
                    # 否定子句（"不要开电视"/"别锁门"）：仅作为排除条件，不生成动作
                    if re.match(r"^(不要|别|不让|不用|跳过)", sub_strip):
                        global_excludes.update(_pe(sub_strip)["exclude_tools"])
                        continue
                    sub_intent = predict_intent(sub_strip, last_intent=None)
                    sub_slots = extract_slots(sub_strip, user_profile)
                    sub_plan = plan(sub_intent, sub_slots, home_state, user_profile)
                    if first_real_intent is None:
                        first_real_intent = sub_intent
                    for s in sub_plan:
                        if s.tool_call and s.tool_call.name in global_excludes:
                            continue
                        step_offset += 1
                        s.step_id = step_offset
                        plan_steps.append(s)
                if first_real_intent is not None:
                    intent = first_real_intent
            else:
                plan_steps = plan(intent, slots, home_state, user_profile)
                # 全句排除：过滤被否定的工具
                if global_excludes:
                    plan_steps = [s for s in plan_steps
                                   if not (s.tool_call and s.tool_call.name in global_excludes)]
                    for i, s in enumerate(plan_steps, start=1):
                        s.step_id = i

    # --- 3. 安全 -------------------------------------------------------
    with timer.stage("safety"):
        tool_calls = [s.tool_call for s in plan_steps if s.tool_call is not None]
        verdicts, needs_conf = evaluate_all(tool_calls, home_state, user_profile)

    # --- 4. 执行 -------------------------------------------------------
    with timer.stage("execute"):
        if confirm:
            tool_results = _execute_plan(plan_steps, verdicts, home_state,
                                          force_execute_high=True)
            session.pending_plan = []
            requires_conf_after = False
        elif needs_conf:
            # 部分动作执行（低风险），高/中风险阻塞等待确认
            tool_results = _execute_plan(plan_steps, verdicts, home_state,
                                          force_execute_high=False)
            session.pending_plan = plan_steps
            session.last_intent = intent
            session.last_slots = slots
            requires_conf_after = True
        else:
            tool_results = _execute_plan(plan_steps, verdicts, home_state)
            session.pending_plan = []
            requires_conf_after = False

    # 紧急场景执行后立即清除标志（emergency_active 仅在当前轮内对 safety 生效）
    if home_state.get("emergency_active"):
        home_state["emergency_active"] = False

    # --- 5. 自然语言回复 ----------------------------------------------
    with timer.stage("reply"):
        reply = _build_reply(intent, plan_steps, verdicts, tool_results,
                              requires_conf_after, home_state)
        # 数值边界越界 → 明确提示
        warnings = home_state.pop("_validation_warnings", [])
        if warnings:
            reply = "⚠️ " + "；".join(warnings) + ("\n" + reply if reply else "")

    session.last_intent = intent
    session.last_slots = slots
    session.history.append({"input": user_input, "intent": intent.name,
                              "reply": reply})
    append_dialog(session_id, "agent", reply)
    kv_set("home_state", home_state)

    response = AgentResponse(
        user_input=user_input,
        intent=intent.to_dict(),
        slots=slots.to_dict() if slots else {},
        plan=[s.to_dict() for s in plan_steps],
        safety=[{"allowed": v.allowed, "risk_level": v.risk_level,
                  "requires_confirmation": v.requires_confirmation,
                  "reason": v.reason} for v in verdicts],
        tool_results=tool_results,
        reply=reply,
        requires_confirmation=requires_conf_after,
        home_state_after=home_state,
        timing_ms={k: round(v, 2) for k, v in timer.timings.items()},
        session_id=session_id,
    )
    return response.to_dict()


if __name__ == "__main__":
    demos = [
        "我准备睡觉了，帮我把家里调整一下",
        "确认",
        "把客厅空调调到 24 度",
        "奶奶摔倒了！",
        "现在家里状态怎么样",
    ]
    sid = new_session_id()
    for d in demos:
        print("\n" + "=" * 60)
        print(">>", d)
        out = run(d, session_id=sid)
        print(json.dumps({"intent": out["intent"], "slots": out["slots"],
                            "reply": out["reply"],
                            "requires_confirmation": out["requires_confirmation"],
                            "timing_ms": out["timing_ms"]},
                          ensure_ascii=False, indent=2))
