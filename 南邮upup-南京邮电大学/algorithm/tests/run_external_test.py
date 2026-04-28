"""跑外部测试集 home_intent_test_100.json。

外部标签是粗粒度的（如 elderly_care 覆盖多个 care.*/safety.* 意图），
本脚本通过 LABEL_MAP 把每个外部 gold_intent 映射到一组『可接受』的系统意图，
任一命中即视为正确。

用法：
    cd algorithm
    ../venv/Scripts/python.exe tests/run_external_test.py
"""
from __future__ import annotations
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_ROOT))

from main import run  # noqa: E402
from src.memory import new_session_id, reset_all  # noqa: E402
from src.edge_opt import benchmark, model_size_report  # noqa: E402


# 外部标签 → 系统内可接受意图集合（任一命中即正确）
LABEL_MAP: dict[str, set[str]] = {
    "sleep_mode": {"mode.sleep"},
    "leave_home_mode": {"mode.leave"},
    "return_home_mode": {"mode.home"},
    "movie_mode": {"mode.movie"},
    "energy_saving_mode": {"mode.energy_save"},
    "security_check": {
        "query.security_check", "query.status", "device.lock",
        "safety.gas_leak", "safety.door_anomaly", "safety.night_intrusion",
    },
    "elderly_care": {
        "care.medicine_remind", "care.fall_emergency", "care.night_companion",
        "care.water_remind", "care.elder_general", "safety.elder_no_response",
    },
    "child_learning": {
        "mode.study", "care.child_study_check", "care.eye_break",
    },
    "environment_adjustment": {
        "device.ac", "device.curtain", "device.light", "device.speaker",
        "device.air_purifier", "device.humidifier", "device.fresh_air",
    },
    "device_control": {
        "device.light", "device.ac", "device.curtain", "device.tv",
        "device.speaker", "device.lock", "device.gas_valve",
        "device.robot_cleaner", "device.air_purifier", "device.humidifier",
        "device.fresh_air", "device.water_heater",
    },
}


def main():
    test_path = _HERE / "home_intent_test_100.json"
    cases = json.load(open(test_path, encoding="utf-8"))
    print(f"加载 {len(cases)} 条外部测试用例：{test_path}")

    reset_all()

    bucket_results: dict[str, list[dict]] = defaultdict(list)
    misses_per_bucket: dict[str, list[dict]] = defaultdict(list)

    for case in cases:
        sid = new_session_id()
        out = run(case["query"], session_id=sid)
        actual = out["intent"]["name"]
        gold = case["gold_intent"]
        accepted = LABEL_MAP.get(gold, set())
        ok = actual in accepted

        rec = {
            "id": case.get("id"),
            "query": case["query"],
            "gold_intent": gold,
            "actual_intent": actual,
            "confidence": out["intent"]["confidence"],
            "ok": ok,
            "plan_steps": len(out.get("plan", [])),
            "requires_confirmation": out.get("requires_confirmation"),
        }
        bucket_results[gold].append(rec)
        if not ok:
            misses_per_bucket[gold].append(rec)

    flat = [r for rs in bucket_results.values() for r in rs]
    total = len(flat)
    overall = sum(1 for r in flat if r["ok"]) / total

    # 端侧延迟基准
    print("\n[正在跑端侧延迟基准 …]")
    bench_sid = new_session_id()
    perf = benchmark(lambda t: run(t, session_id=bench_sid),
                      [c["query"] for c in cases])
    sizes = model_size_report()

    report = {
        "summary": {
            "total_cases": total,
            "overall_accuracy": round(overall, 4),
        },
        "performance": perf,
        "sizes_mb": sizes,
        "buckets": {b: rs for b, rs in bucket_results.items()},
        "label_mapping": {k: sorted(list(v)) for k, v in LABEL_MAP.items()},
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    out_path = _HERE / "report_external.json"
    json.dump(report, open(out_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    # ---- 控制台汇总 ----
    print()
    print("=" * 70)
    print("外部测试集报告（home_intent_test_100.json）")
    print("=" * 70)
    print(f"总用例：{total}")
    print(f"整体准确率：{overall:.2%}")
    print()
    print("分桶准确率：")
    for b, rs in bucket_results.items():
        ok = sum(1 for r in rs if r["ok"])
        print(f"  {b:25s}: {ok}/{len(rs)} = {ok/len(rs):.2%}")
    print()
    print("端侧延迟（毫秒）：")
    for k, v in perf["latency_ms"].items():
        print(f"  {k}: {v}")
    print(f"内存峰值：{perf['memory_mb']['peak']} MB")
    print()
    if any(misses_per_bucket.values()):
        print("典型未命中样本（每桶前 3 条）：")
        for b, ms in misses_per_bucket.items():
            if not ms:
                continue
            print(f"  [{b}]")
            for m in ms[:3]:
                print(f"    {m['id']} {m['query'][:40]}")
                print(f"       gold={m['gold_intent']}  pred={m['actual_intent']} conf={m['confidence']:.2f}")
    print()
    print(f"详细报告：{out_path}")


if __name__ == "__main__":
    main()
