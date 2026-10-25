#!/usr/bin/env python3
"""S5-04 片尾字卡：黑金风格 + 二创声明 + 淡入淡出，产物 build/shots/S5-04.mp4
（4.0s / 1080x1920 / 24fps / 静音），assemble2 将其按真实镜头使用 → 40/40。
命令行仅 ffmpeg：字面前缀 + 显式 shell=False，参数全部来自本模块常量。
"""
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
W, H = 1080, 1920
GOLD, INK, GREY = (212, 175, 55), (12, 12, 16), (158, 158, 166)


def load_font(size):
    for p in ["/System/Library/Fonts/PingFang.ttc",
              "/System/Library/Fonts/STHeiti Light.ttc",
              "/System/Library/Fonts/Hiragino Sans GB.ttc"]:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    sys.exit("[endcard] 无 CJK 字体")


def main():
    img = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(img)
    f_title, f_sub, f_body, f_tiny = (load_font(s) for s in (110, 48, 40, 30))
    d.rectangle([0, 0, W, 10], fill=GOLD)

    def center(text, font, y, fill):
        d.text(((W - d.textlength(text, font=font)) / 2, y), text,
               font=font, fill=fill)

    center("风 起 金 陵", f_title, 620, GOLD)
    center("《琅琊榜》第一集 · 短剧化改编", f_sub, 800, (235, 232, 224))
    d.line([(W / 2 - 160, 900), (W / 2 + 160, 900)], fill=GOLD, width=2)
    center("40/40 镜头 · 39 条 AI 视频 · 22 条分角色配音", f_body, 960, GREY)
    center("minimax-h3-max 文生视频 × gpt-image-2 × cloud TTS", f_body, 1030, GREY)
    center("七牛第五届 1024 Hackathon · XCanvas 议题", f_body, 1100, GREY)

    y = 1500
    for line in ["原著《琅琊榜》版权归海宴及相关权利方所有",
                 "本片为内部 Hackathon 演示用途的二创改编",
                 "不对外发布 · 不作商业使用"]:
        center(line, f_tiny, y, (120, 120, 128))
        y += 54
    out_png = BUILD / "endcard_S5-04.png"
    img.save(out_png)

    args = ["-loop", "1", "-t", "4.0", "-i", str(out_png), "-vf",
            "scale=1080:1920,fps=24,format=yuv420p,"
            "fade=t=in:st=0:d=0.8,fade=t=out:st=3.5:d=0.5",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-an",
            str(BUILD / "shots" / "S5-04.mp4")]
    subprocess.run(["ffmpeg", "-y", "-v", "error"] + args,
                   check=True, shell=False)
    print("endcard -> build/shots/S5-04.mp4")


if __name__ == "__main__":
    main()
