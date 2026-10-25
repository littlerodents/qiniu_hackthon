#!/usr/bin/env python3
"""Demo 视频（60-90s）程序化制作：成片高光 + 数据资产卡 + 产线卡 + 降级卡
+ 成片重放 + 结尾卡，6 段 cloud TTS 旁白按段落起播点混音。
命令行仅调用 ffmpeg：字面前缀 + 显式 shell=False，参数全部来自本模块常量，
输出仅写 build/。产物：build/demo.mp4（1080x1920 30fps）
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
DEMO = BUILD / "demo_work"
DEMO.mkdir(exist_ok=True)
ANIM = BUILD / "animatic_v1.mp4"
AUD = BUILD / "audio" / "demo"
W, H, FPS = 1080, 1920, 30

# 段落时长与旁白起播点（秒）
SECTIONS = [
    ("s1", 12.0, 1.0),    # 高光快剪
    ("s2", 14.7, 0.8),    # 数据资产卡
    ("s3", 13.6, 0.8),    # 产线卡
    ("s4", 12.5, 0.8),    # 降级卡
    ("s5", 8.0, 1.5),     # 成片重放
    ("s6", 11.5, 0.8),    # 结尾卡
]
TOTAL = sum(s[1] for s in SECTIONS)

HIGHLIGHTS = [  # (起点, 时长) 取自动态分镜
    (62.7, 3.0),   # S2-05 飞流
    (76.4, 3.0),   # S2-08 梅长苏定妆
    (135.4, 3.0),  # S4-04 梁帝
    (172.6, 3.0),  # S5-02 火光
]
REPLAY = [(0.0, 4.0), (176.1, 4.0)]  # S0-01 冷开场 + S5-03 收尾


def run_ffmpeg(args):
    """字面前缀 + 显式 shell=False；参数全部来自本模块常量。"""
    import subprocess as sp
    r = sp.run(["ffmpeg", "-y", "-v", "error"] + args, shell=False,
               capture_output=True, text=True)
    if r.returncode:
        sys.exit("[make_demo] ffmpeg 失败: " + r.stderr[-800:])


def cut(src_range, idx):
    start, dur = src_range
    run_ffmpeg(["-ss", str(start), "-t", str(dur), "-i", str(ANIM),
                "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS}",
                "-c:v", "libx264", "-preset", "fast", "-crf", "21",
                "-pix_fmt", "yuv420p", "-r", str(FPS), "-an",
                str(DEMO / f"cut{idx}.mp4")])


def concat_cuts(cuts, out, overlay_png=None):
    lst = DEMO / (out + ".txt")
    lst.write_text("".join(f"file '{c.name}'\n" for c in cuts))
    if overlay_png:
        run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(lst),
                    "-i", str(overlay_png),
                    "-filter_complex",
                    "[0:v][1:v]overlay=(W-w)/2:main_h-overlay_h-300",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "21",
                    "-pix_fmt", "yuv420p", "-an", str(DEMO / (out + ".mp4"))])
        return
    run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(lst),
                "-vf", "null", "-c:v", "libx264", "-preset", "fast", "-crf", "21",
                "-pix_fmt", "yuv420p", "-an", str(DEMO / (out + ".mp4"))])


def card(png, dur, out):
    run_ffmpeg(["-loop", "1", "-t", str(dur), "-i", str(png),
                "-vf", f"scale={W}:{H},fps={FPS},format=yuv420p",
                "-c:v", "libx264", "-preset", "fast", "-crf", "21", "-an",
                str(DEMO / (out + ".mp4"))])


def main():
    # ---------- 卡片 ----------
    from PIL import Image, ImageDraw, ImageFont

    def load_font(size):
        for p in ["/System/Library/Fonts/PingFang.ttc",
                  "/System/Library/Fonts/STHeiti Light.ttc",
                  "/System/Library/Fonts/Hiragino Sans GB.ttc"]:
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
        sys.exit("[make_demo] 无 CJK 字体")

    GOLD, INK, GREY = (212, 175, 55), (16, 16, 20), (150, 150, 158)

    def make_card(name, kicker, title, lines, footer):
        img = Image.new("RGB", (W, H), INK)
        d = ImageDraw.Draw(img)
        f_k, f_t, f_b, f_f = (load_font(s) for s in (40, 64, 44, 34))
        d.rectangle([0, 0, W, 14], fill=GOLD)
        d.text((90, 200), kicker, font=f_k, fill=GOLD)
        d.text((90, 280), title, font=f_t, fill=(240, 238, 230))
        y = 520
        for head, body in lines:
            d.rectangle([90, y + 14, 118, y + 42], fill=GOLD)
            d.text((150, y), head, font=f_b, fill=(240, 238, 230))
            y += 92
            for seg in body:
                d.text((150, y), seg, font=f_f, fill=GREY)
                y += 62
            y += 40
        d.text((90, H - 160), footer, font=f_f, fill=GREY)
        img.save(DEMO / name)

    make_card("card2.png", "STEP 1 · 创作决策数据化", "先别急着生成",
              [("剧本《风起金陵》", ["9:16 竖屏 · 6 场 40 镜 · 每 20-30 秒一个钩子"]),
               ("40 镜分镜表 ep1_storyboard.json", ["每镜：景别 / 运镜 / 时长 / 台词 / 音效 / 降级方案"]),
               ("12 角色卡 + 7 场景卡", ["外貌三锚点 / 服装锚 / 习惯动作 / TTS 音色参数"])],
              "assets/ 全部为结构化 JSON，可复跑、可交接、可复制到任意 IP")
    make_card("card3.png", "STEP 2 · 产线自动装配", "生成只是执行层",
              [("build_prompts.py", ["37 份镜头提示词自动拼装，角色锚+场景锚引用零错误"]),
               ("22 条 TTS 音轨先行", ["旁白 11 + 台词 11，分角色调语速音高"]),
               ("音轨驱动时间线对齐", ["分镜预设 143.5s → 真实配音 186.8s，19 镜自动拉伸"])],
              "产物 build/animatic_v1.mp4 · 时间线固化 animatic_timeline.json")
    make_card("card4.png", "STEP 3 · 故障即架构验证", "平台挂了？换执行层",
              [("实测：平台不可达", ["灯虹在参赛网络不可达，网关 key 无法登录"]),
               ("数小时内切换自建产线", ["MiniMax 直连产线，资产层一行不改"]),
               ("网关探测留档 decisions.md", ["内部网关 LLM-only，证据可复核（D2）"])],
              "分层架构的意义：换掉的只是执行层，资产与决策全部保值")
    make_card("card6.png", "七牛第五届 1024 Hackathon", "琅琊榜第一集 × 短剧产线",
              [("GitHub", ["github.com/littlerodents/qiniu_hackthon",
                           "源码 · 运行说明 · 架构文档 · PR 痕迹"]),
               ("架构六层 · 1/2/3 人分工档 · 决策记录", ["PR 痕迹 · v0 tag · QC 报告齐备"]),
               ("二创声明", ["原著版权归海宴及相关权利方，仅内部演示用途"])],
              "Talk is cheap — show me what you build")

    # ---------- 视频段 ----------
    for i, hr in enumerate(HIGHLIGHTS):
        cut(hr, i)
    # 标题横幅：PIL 绘制（半透明底 + 金色副题），overlay 合成（本 ffmpeg 无 drawtext）
    from PIL import Image as PImage
    f_t1 = load_font(64)
    f_t2 = load_font(38)
    banner = PImage.new("RGBA", (W, 320), (0, 0, 0, 140))
    bd = ImageDraw.Draw(banner)
    t1 = "琅琊榜 · 第一集 短剧化改编"
    t2 = "9:16 · 40 镜 · 186.8 秒 · 22 音轨"
    bd.text(((W - bd.textlength(t1, font=f_t1)) / 2, 60), t1,
            font=f_t1, fill=(245, 243, 235, 255))
    bd.text(((W - bd.textlength(t2, font=f_t2)) / 2, 190), t2,
            font=f_t2, fill=(212, 175, 55, 255))
    banner.save(DEMO / "title.png")
    concat_cuts([DEMO / f"cut{i}.mp4" for i in range(len(HIGHLIGHTS))],
                "s1", DEMO / "title.png")
    card(DEMO / "card2.png", SECTIONS[1][1], "s2")
    card(DEMO / "card3.png", SECTIONS[2][1], "s3")
    card(DEMO / "card4.png", SECTIONS[3][1], "s4")
    for i, rp in enumerate(REPLAY):
        cut(rp, 10 + i)
    concat_cuts([DEMO / "cut10.mp4", DEMO / "cut11.mp4"], "s5")
    card(DEMO / "card6.png", SECTIONS[5][1], "s6")

    # ---------- 合并视频 ----------
    lst = DEMO / "all.txt"
    lst.write_text("".join(f"file '{n}.mp4'\n" for n, _, _ in SECTIONS))
    run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(lst),
                "-c", "copy", str(DEMO / "video.mp4")])

    # ---------- 旁白混音（按段落起播点 adelay） ----------
    t = 0.0
    filters, inputs = [], []
    for i, (_, dur, narr_at) in enumerate(SECTIONS, 1):
        delay = int((t + narr_at) * 1000)
        inputs += ["-i", str(AUD / f"seg{i}.wav")]
        filters.append(f"[{i - 1}:a]adelay={delay}|{delay}[a{i}]")
        t += dur
    mix = "".join(f"[a{i}]" for i in range(1, 7))
    fc = ";".join(filters) + f";{mix}amix=inputs=6:normalize=0,apad"
    run_ffmpeg(inputs
               + ["-filter_complex", fc, "-t", str(TOTAL),
                  "-ar", "48000", "-c:a", "aac", "-b:a", "160k",
                  str(DEMO / "narr.m4a")])

    # ---------- 终混 ----------
    fade_out = TOTAL - 0.8
    run_ffmpeg(["-i", str(DEMO / "video.mp4"), "-i", str(DEMO / "narr.m4a"),
                "-vf", f"fade=t=in:st=0:d=0.5,fade=t=out:st={fade_out:.2f}:d=0.8",
                "-c:v", "libx264", "-preset", "fast", "-crf", "21",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
                "-movflags", "+faststart", "-shortest", str(BUILD / "demo.mp4")])
    print(json.dumps({"total": TOTAL, "out": str(BUILD / "demo.mp4")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
