"""一次性下载小型中文嵌入模型到本地，运行时不再联网。

模型选择：BAAI/bge-small-zh-v1.5
- 体积：~95 MB（int8 量化版可压到 ~30 MB，但保留 fp32 以维持精度）
- 维度：512
- 中文优化，适合家居场景短文本
- 支持 CPU 推理，单条 < 30 ms
"""
from __future__ import annotations
import os
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models" / "embedder"
MODEL_NAME = "BAAI/bge-small-zh-v1.5"


def main():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    if (MODELS_DIR / "config.json").exists():
        print(f"[skip] 模型已存在于 {MODELS_DIR}")
        return
    print(f"[download] 拉取 {MODEL_NAME} -> {MODELS_DIR} ...")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL_NAME, cache_folder=str(ROOT / "models" / "_hf_cache"))
    model.save(str(MODELS_DIR))
    # 清理 HF 缓存以节省提交包体
    cache = ROOT / "models" / "_hf_cache"
    if cache.exists():
        shutil.rmtree(cache, ignore_errors=True)
    print(f"[done] 模型已保存到 {MODELS_DIR}")
    total = sum(f.stat().st_size for f in MODELS_DIR.rglob("*") if f.is_file())
    print(f"[size] {total / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
