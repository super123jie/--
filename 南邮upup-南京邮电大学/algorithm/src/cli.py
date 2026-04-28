"""命令行交互式 Demo（无依赖于 streamlit，便于答辩备用）。"""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import run  # noqa: E402
from src.memory import new_session_id  # noqa: E402


def main():
    sid = new_session_id()
    print(f"=== HomeCare-Agent CLI Demo === session={sid}")
    print("输入 :q 退出，输入 :reset 重置会话，输入 :s 查看状态")
    while True:
        try:
            line = input("\n>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line == ":q":
            break
        if line == ":reset":
            sid = new_session_id()
            print(f"new session: {sid}")
            continue
        if line == ":s":
            out = run("现在家里状态怎么样", session_id=sid)
            print(out["reply"])
            continue
        out = run(line, session_id=sid)
        print(f"[意图] {out['intent']['name']} (置信度 {out['intent']['confidence']:.2f})")
        if out["slots"]:
            print(f"[槽位] {json.dumps(out['slots'], ensure_ascii=False)}")
        if out["plan"]:
            print(f"[计划] {len(out['plan'])} 步")
        print(f"[耗时] {sum(out['timing_ms'].values()):.1f} ms")
        print(f"\n>> {out['reply']}")


if __name__ == "__main__":
    main()
