# -*- coding: utf-8 -*-
"""生成应用图标 assets/app.ico（仅打包期使用，Pillow 不参与运行时逻辑）。"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "app.ico"


def font(size: int):
    for p in (r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\segoeuib.ttf",
              r"C:\Windows\Fonts\msyhbd.ttc"):
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def main():
    S = 256
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # 蓝色文档底 + 折角
    d.rounded_rectangle((36, 20, 220, 236), radius=18, fill=(31, 78, 121, 255),
                        outline=(21, 56, 92, 255), width=4)
    d.polygon([(172, 20), (220, 68), (172, 68)], fill=(122, 165, 205, 255))
    d.rounded_rectangle((58, 96, 198, 158), radius=10, fill=(255, 255, 255, 235))
    f = font(46)
    text = "PDF"
    box = d.textbbox((0, 0), text, font=f)
    d.text(((S - (box[2] - box[0])) / 2 - box[0], 100), text, font=f, fill=(31, 78, 121, 255))
    # 三条信息行
    for i, w in enumerate((120, 96, 108)):
        y = 178 + i * 18
        d.rounded_rectangle((58, y, 58 + w, y + 8), radius=4, fill=(200, 222, 242, 255))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("icon ->", OUT, OUT.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
