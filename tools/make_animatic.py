#!/usr/bin/env python3
"""动态分镜（Animatic）生成器：分镜卡画面 + 真实 TTS 音轨 → 可看的整片 v1。

1. 读取分镜表与 build/audio/ 下已生成的旁白/台词音轨
2. 每镜时长 = max(分镜时长, 该镜音轨总长 + 呼吸间隔) —— 音轨驱动对齐
3. PIL 渲染 9:16 分镜卡（场记信息 + 画面描述 + 台词）
4. ffmpeg 拼装 1080x1920@24 成片 + 混音，输出 build/animatic_v1.mp4
5. 输出 build/animatic_timeline.json（后续 MiniMax 生成阶段的时长事实来源）

用法: python3 tools/make_animatic.py   （仓库根目录执行）
"""
import json
import subprocess
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
AUDIO = ROOT / "build" / "audio"
WORK = ROOT / "build" / "animatic_frames"
OUT_MP4 = ROOT / "build" / "animatic_v1.mp4"
OUT_TL = ROOT / "build" / "animatic_timeline.json"
W, H, FPS = 1080, 1920, 24
FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
]
SCENE_COLOR = {
    "meiling": (120, 40, 40), "langya_pavilion": (170, 150, 100),
    "langzhou_dock": (90, 120, 140), "jinling_city": (170, 120, 60),
    "cabin_night": (140, 100, 60), "ningguo_manor": (150, 60, 60),
    "palace_hall": (180, 150, 50),
}
SPEAKER_CN = {"narrator": "旁白", "meichangsu": "梅长苏", "feiliu": "飞流",
              "xiaojingrui": "萧景睿", "yanyujin": "言豫津", "jiying": "季赢",
              "liangdi": "梁帝", "niuhuang": "霓凰", "gaozhan": "高湛",
              "taizi": "太子", "yuwang": "誉王", "langye_master": "琅琊阁主", "ligang": "黎纲"}
# 镜头号 → 该镜音轨（相对 build/audio/，按时序排列）
SHOT_AUDIO = {
    "S0-01": ["narrator/S0-01.wav"], "S0-03": ["narrator/S0-03.wav"],
    "S1-01": ["narrator/S1-01.wav"], "S1-04": ["narrator/S1-04.wav"],
    "S1-06": ["narrator/S1-06.wav"], "S2-01": ["narrator/S2-01.wav"],
    "S2-02": ["jiying/S2-02.wav"], "S2-07": ["jiying/S2-07.wav"],
    "S2-08": ["meichangsu/S2-08.wav"],
    "S2-09": ["xiaojingrui/S2-09.wav", "yanyujin/S2-09b.wav"],
    "S2-10": ["narrator/S2-10.wav"], "S3-02": ["yanyujin/S3-02.wav", "meichangsu/S3-02b.wav"],
    "S3-03": ["narrator/S3-03.wav"], "S3-05": ["xiaojingrui/S3-05.wav"],
    "S4-03": ["gaozhan/S4-03.wav"], "S4-04": ["liangdi/S4-04.wav"],
    "S4-06": ["narrator/S4-06.wav"], "S4-07": ["narrator/S4-07.wav"],
    "S4-08": ["liangdi/S4-08.wav"], "S5-03": ["narrator/S5-03.wav"],
}
PAD = 0.7  # 音轨后呼吸秒数


def ffprobe_dur(p: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    return float(r.stdout.strip())


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for f in FONT_CANDIDATES:
        if Path(f).exists():
            try:
                return ImageFont.truetype(f, size)
            except Exception:
                continue
    raise SystemExit("未找到中文字体")


def wrap_cn(draw, text, font, max_w):
    lines, line = [], ""
    for ch in text:
        if draw.textlength(line + ch, font=font) <= max_w:
            line += ch
        else:
            lines.append(line)
            line = ch
    if line:
        lines.append(line)
    return lines or [""]


def render_card(shot, scene_name, dur):
    img = Image.new("RGB", (W, H), (32, 38, 50))
    d = ImageDraw.Draw(img)
    accent = SCENE_COLOR.get(shot["scene"], (120, 120, 120))
    d.rectangle([0, 0, W, 14], fill=accent)
    f_big, f_mid, f_small = load_font(72), load_font(44), load_font(34)
    d.text((70, 120), shot["id"], font=f_big, fill=accent)
    d.text((70, 230), f"{scene_name} · {dur:.1f}s", font=f_mid, fill=(210, 210, 210))
    y = 420
    for line in wrap_cn(d, shot["action"], f_mid, W - 140):
        d.text((70, y), line, font=f_mid, fill=(235, 235, 235))
        y += 66
    y += 60
    for dlg in shot.get("dialogue", []):
        who = SPEAKER_CN.get(dlg["char"], dlg["char"])
        text = f"{who}：{dlg['line']}"
        for line in wrap_cn(d, text, f_small, W - 140):
            d.text((70, y), line, font=f_small, fill=accent)
            y += 52
        y += 16
    d.text((70, H - 130), "琅琊榜 EP1 · 风起金陵 — 动态分镜 v1", font=f_small, fill=(110, 110, 110))
    return img


def main():
    board = json.loads((ROOT / "assets/storyboard/ep1_storyboard.json").read_text(encoding="utf-8"))
    scenes = {s["id"]: s["name"] for s in json.loads((ROOT / "assets/scenes.json").read_text(encoding="utf-8"))["scenes"]}
    WORK.mkdir(parents=True, exist_ok=True)

    timeline, audio_jobs, t = [], [], 0.0
    for shot in board["shots"]:
        tracks = SHOT_AUDIO.get(shot["id"], [])
        durs = [ffprobe_dur(AUDIO / rel) for rel in tracks]
        need = (sum(durs) + PAD * len(durs)) if durs else 0.0
        dur = max(shot["dur"], round(need + 0.2, 1))
        render_card(shot, scenes.get(shot["scene"], shot["scene"]), dur).save(WORK / f"{shot['id']}.png")
        off = t + 0.35
        for rel, ad in zip(tracks, durs):
            audio_jobs.append({"file": str(AUDIO / rel), "at": round(off, 2), "len": round(ad, 2)})
            off += ad + PAD
        timeline.append({"id": shot["id"], "storyboard_dur": shot["dur"], "final_dur": dur,
                         "stretched": dur > shot["dur"] + 0.01, "audio": len(durs)})
        t += dur
    total = round(t, 2)
    OUT_TL.write_text(json.dumps({"total": total, "shots": timeline, "audio_jobs": audio_jobs},
                                 ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "build" / "animatic_timeline.js").write_text(
        "window.ANIMATIC_TIMELINE = " + json.dumps(
            {"total": total, "shots": timeline}, ensure_ascii=False) + ";\n", encoding="utf-8")
    print(f"40 镜对齐完成，总时长 {total}s（分镜表预设 143.5s），拉伸镜头 "
          f"{sum(1 for s in timeline if s['stretched'])} 个")

    # 视频轨：concat demuxer
    concat = WORK / "list.txt"
    concat.write_text("".join(f"file '{s['id']}.png'\nduration {s['final_dur']}\n"
                              for s in timeline) + f"file '{timeline[-1]['id']}.png'\n", encoding="utf-8")
    silent = WORK / "silent.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                    "-i", str(concat), "-vf", f"scale={W}:{H},format=yuv420p,fps={FPS}",
                    "-c:v", "libx264", "-preset", "fast", str(silent)], check=True)

    # 音频轨：逐条 adelay 后 amix
    inputs, filters = [], []
    for j, job in enumerate(audio_jobs, start=1):  # 输入 0 是无声视频，音轨从 1 起
        inputs += ["-i", job["file"]]
        filters.append(f"[{j}:a]adelay={int(job['at'] * 1000)}|{int(job['at'] * 1000)}[a{j}]")
    mix = "".join(f"[a{j}]" for j in range(1, len(audio_jobs) + 1))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(silent), *inputs,
                    "-filter_complex", ";".join(filters)
                    + f";{mix}amix=inputs={len(audio_jobs)}:normalize=0,apad=whole_dur={total}[aout]",
                    "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-t", str(total), str(OUT_MP4)], check=True)
    print(f"成片 -> {OUT_MP4}")


if __name__ == "__main__":
    main()
