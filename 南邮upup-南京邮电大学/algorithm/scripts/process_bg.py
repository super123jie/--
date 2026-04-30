"""一次性处理参考户型图：抹掉文字卡片，保留 3D 坊期与设备本体。

输入：E:/1/中兴/智能家居图.png（1448x1086 RGB）
输出：algorithm/static/bg_floorplan.png（同尺寸 RGBA，文字模糊后）

策略：
1. 在已知文字卡片位置（基于原图肉眼标注的相对坐标）应用 GaussianBlur(20)
2. 整图轻微降亮度 80% + 蓝紫色调匹配深色 UI
3. 保存 PNG（带 alpha）
"""
from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageFilter, ImageEnhance, ImageDraw

# 源 / 目标
SRC = Path(r"E:/1/中兴/智能家居图.png")
DST = Path(__file__).resolve().parent.parent / "static" / "bg_floorplan.png"
DST.parent.mkdir(parents=True, exist_ok=True)

# 已知文字卡片矩形：每个矩形 (x0, y0, x1, y1) 单位为相对比例（0-1）
# 对照参考图肉眼标注：
TEXT_CARDS = [
    (0.00, 0.00, 0.18, 0.18),   # 左上：客厅卡片
    (0.30, 0.00, 0.50, 0.20),   # 中上：主卧卡片
    (0.65, 0.00, 0.92, 0.20),   # 右上：次卧卡片
    (0.40, 0.18, 0.60, 0.32),   # 中：儿童房卡片
    (0.78, 0.18, 1.00, 0.40),   # 右中：厨房卡片
    (0.00, 0.50, 0.20, 0.65),   # 左：全屋卡片
    (0.00, 0.85, 0.45, 1.00),   # 左下：全屋安全
    (0.40, 0.05, 0.55, 0.18),   # 智能中枢
]


def main():
    img = Image.open(SRC).convert("RGB")
    W, H = img.size

    # 第 1 步：抹掉文字卡片区域 —— 在每个矩形里提取那块图，重度模糊后贴回
    for x0, y0, x1, y1 in TEXT_CARDS:
        box = (int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H))
        region = img.crop(box).filter(ImageFilter.GaussianBlur(radius=22))
        img.paste(region, box)

    # 第 2 步：整图调色 —— 略降亮度、轻微蓝紫色调、提高对比度
    img = ImageEnhance.Brightness(img).enhance(0.85)
    img = ImageEnhance.Contrast(img).enhance(1.10)

    # 蓝紫色调：与原图融合一层 #1a1d3a 半透明
    tint = Image.new("RGB", img.size, (26, 29, 58))
    img = Image.blend(img, tint, alpha=0.18)

    # 第 3 步：转 RGBA 加全图 alpha=235（让顶层 UI 略透）
    img = img.convert("RGBA")
    alpha = Image.new("L", img.size, 235)
    img.putalpha(alpha)

    # 缩到 1280×960 再导出，控制文件大小
    target_w = 1280
    target_h = int(H * target_w / W)
    img = img.resize((target_w, target_h), Image.LANCZOS)

    img.save(DST, "PNG", optimize=True)
    size_kb = DST.stat().st_size / 1024
    print(f"OK: {DST} ({target_w}x{target_h}, {size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
