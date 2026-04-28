"""端侧资源监测与延迟统计。

提供两类工具：
- StageTimer 上下文管理器，记录每阶段耗时；
- benchmark() 跑批量样本输出 P50/P95/P99 + 内存峰值，用于 README 表格。
"""
from __future__ import annotations
import json
import time
import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import psutil


@dataclass
class StageTimer:
    timings: dict = field(default_factory=dict)

    @contextmanager
    def stage(self, name: str):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.timings[name] = (time.perf_counter() - t0) * 1000.0


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * pct
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    if lo == hi:
        return s[lo]
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def benchmark(run_fn: Callable[[str], dict], inputs: list[str]) -> dict:
    """运行 inputs 全量并采集延迟与内存。"""
    proc = psutil.Process(os.getpid())
    mem_start = proc.memory_info().rss / 1024 / 1024
    mem_peak = mem_start
    latencies = []
    cpu_samples = []
    for txt in inputs:
        proc.cpu_percent(None)
        t0 = time.perf_counter()
        run_fn(txt)
        latencies.append((time.perf_counter() - t0) * 1000.0)
        cpu_samples.append(proc.cpu_percent(None))
        mem_peak = max(mem_peak, proc.memory_info().rss / 1024 / 1024)
    return {
        "samples": len(inputs),
        "latency_ms": {
            "p50": round(_percentile(latencies, 0.50), 2),
            "p95": round(_percentile(latencies, 0.95), 2),
            "p99": round(_percentile(latencies, 0.99), 2),
            "mean": round(sum(latencies) / len(latencies), 2),
            "max": round(max(latencies), 2),
        },
        "memory_mb": {
            "start": round(mem_start, 1),
            "peak": round(mem_peak, 1),
            "delta": round(mem_peak - mem_start, 1),
        },
        "cpu_percent_avg": round(sum(cpu_samples) / len(cpu_samples), 1) if cpu_samples else 0.0,
    }


def model_size_report() -> dict:
    """统计 models/ 与 data_local/ 占用。"""
    base = Path(__file__).resolve().parent.parent
    out = {}
    for sub in ("models", "data_local"):
        p = base / sub
        if not p.exists():
            out[sub] = 0.0
            continue
        total = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
        out[sub] = round(total / 1024 / 1024, 3)
    return out
