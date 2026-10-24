#!/usr/bin/env python3
"""MiniMax 直连产线：关键帧图像 → 图生视频 → 成片合成（v2）。

凭据只从环境变量读取（MINIMAX_API_KEY / MINIMAX_GROUP_ID，可选 MINIMAX_API_HOST），
绝不写入仓库。本机代理对 API 域名可能不通：不使用系统代理，而是 DoH(223.5.5.5)
解析真实 IP 后在进程内做 hosts 映射（getaddrinfo 补丁），requests 直连 + 正常 SNI。

安全边界（防注入/SSRF/越界写）：
- 出网仅限 https + 域名后缀白名单，解析出的 IP 阻断私网/环回/链路本地/保留段；
- 禁止重定向；task_id/file_id/镜头号等外部数据全部白名单校验后才进入路径；
- 文件写入仅限本仓库 build/ 目录；命令行只调用 ffmpeg 且参数全部来自仓库内已校验数据。

子命令:
  probe                 探测连通性/模型可用性（先跑这个）
  images  [--limit N]   按 build/prompts/ 逐镜生成关键帧 → build/frames/<id>.png
  videos  [--limit N]   逐镜图生视频 → build/shots/<id>.mp4
  assemble2             用真实镜头替换分镜卡，按音轨时间线合成 build/final_v2.mp4

模型名与端点默认值可能随平台演进——全部可用环境变量覆盖:
  MM_IMAGE_MODEL(默认 image-01) MM_VIDEO_MODEL(默认 video-01)
  MINIMAX_API_HOST(默认 api.minimax.chat)
probe 不通时先改环境变量，不要改代码默认值。
"""
import base64
import ipaddress
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"

API_HOST = os.environ.get("MINIMAX_API_HOST", "api.minimax.chat")
API_KEY = os.environ.get("MINIMAX_API_KEY", "")
GROUP_ID = os.environ.get("MINIMAX_GROUP_ID", "")
IMAGE_MODEL = os.environ.get("MM_IMAGE_MODEL", "image-01")
VIDEO_MODEL = os.environ.get("MM_VIDEO_MODEL", "video-01")

RE_IP = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
RE_HOST = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)*$")
RE_SHOT = re.compile(r"^S\d-\d{2}$")
ALLOWED_HOST_SUFFIXES = (".minimax.chat", ".minimaxi.com", ".qiniu.io", ".qiniu.com", ".qnlinking.com")
ALLOWED_DIRS = (str(BUILD.resolve()),)


def die(msg):
    raise SystemExit("[minimax_pipeline] " + msg)


def is_safe_host(h: str) -> bool:
    return bool(h) and bool(RE_HOST.match(h)) and h.endswith(ALLOWED_HOST_SUFFIXES)


def is_safe_ip(ip: str) -> bool:
    """阻断私网/环回/链路本地/保留/组播段，防 SSRF 与 DNS rebinding。"""
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (a.is_private or a.is_loopback or a.is_link_local or a.is_reserved
                or a.is_multicast or a.is_unspecified)


def check(cond, label, value):
    if not cond:
        die(label + " 校验失败: " + str(value)[:120])
    return value


def doh_resolve(host: str) -> str:
    """AliDNS DoH 解析真实 IP（HTTPS GET，返回值经 IP 字面量+边界校验）。"""
    with urllib.request.urlopen("https://223.5.5.5/resolve?name=" + host + "&type=A", timeout=10) as r:
        data = json.loads(r.read().decode())
    ip = [a["data"] for a in data.get("Answer", []) if a.get("type") == 1][0]
    check(RE_IP.match(ip), "DoH返回IP格式", ip)
    check(is_safe_ip(ip), "DoH返回IP边界", ip)
    return ip


_real_getaddrinfo = socket.getaddrinfo


def patched_getaddrinfo(host, port, *args, **kwargs):
    """进程内 hosts 映射：白名单域名指到 DoH 真实 IP，绕开本机 fake-IP 代理。"""
    if is_safe_host(host):
        cache = BUILD / ("mm_ip_" + host.replace(".", "_") + ".txt")
        if cache.exists() and time.time() - cache.stat().st_mtime < 600:
            ip = check(RE_IP.match(cache.read_text().strip()), "缓存IP格式", cache)
            check(is_safe_ip(ip), "缓存IP边界", ip)
        else:
            ip = doh_resolve(host)
            cache.write_text(ip)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]
    return _real_getaddrinfo(host, port, *args, **kwargs)


socket.getaddrinfo = patched_getaddrinfo


def http(method: str, url: str, payload=None, timeout=120, binary=False):
    """仅 https + 白名单域名直连（不走系统代理、禁重定向），返回 JSON 或响应体。"""
    check(method in ("GET", "POST"), "HTTP方法", method)
    parts = urlsplit(url)
    check(parts.scheme == "https", "协议必须https", url)
    check(is_safe_host(parts.hostname or ""), "请求域名", url)
    ip = patched_getaddrinfo(parts.hostname, 443, socket.AF_INET)[0][4][0]
    check(is_safe_ip(ip), "解析IP边界", ip)
    if not API_KEY:
        die("缺少 MINIMAX_API_KEY 环境变量（凭据不入库，只走环境变量）")
    ses = requests.Session()
    ses.trust_env = False
    r = ses.request(method, url, json=payload, timeout=timeout, allow_redirects=False,
                    headers={"Authorization": "Bearer " + API_KEY,
                             "Content-Type": "application/json"})
    if binary:
        return r
    try:
        return r.json()
    except ValueError:
        die("非 JSON 响应 HTTP " + str(r.status_code) + ": " + r.text[:300])


def api(path: str, payload=None):
    check(re.match(r"^/v1/[a-z0-9_]+(/[a-z0-9_]+)*(\?[a-zA-Z_=&0-9]*)?$", path), "API路径", path)
    return http("POST" if payload is not None else "GET", "https://" + API_HOST + path, payload)


def gen_shots():
    board = json.loads((ROOT / "assets/storyboard/ep1_storyboard.json").read_text(encoding="utf-8"))
    manifest = json.loads((BUILD / "prompts/manifest.json").read_text())["manifest"]
    prompts = {m["id"]: m for m in manifest if m["type"] == "gen"}
    return [(s["id"], (ROOT / prompts[s["id"]]["prompt_file"]).read_text().strip(), s)
            for s in board["shots"] if s["id"] in prompts]


def safe_out(rel: str) -> Path:
    p = (BUILD / rel).resolve()
    check(str(p).startswith(ALLOWED_DIRS), "输出路径越界", rel)
    return p


def cmd_probe():
    print("host=" + API_HOST + " image=" + IMAGE_MODEL + " video=" + VIDEO_MODEL
          + " group=" + ("set" if GROUP_ID else "unset"))
    print("连通性(DoH+进程内hosts直连):", doh_resolve(API_HOST))
    res = api("/v1/text/chatcompletion_v2",
              {"model": os.environ.get("MM_LLM_MODEL", "abab6.5s-chat"),
               "messages": [{"role": "user", "content": "回复OK两个字母即可"}]})
    print("LLM 探测:", json.dumps(res, ensure_ascii=False)[:400])


def cmd_images(limit):
    (BUILD / "frames").mkdir(parents=True, exist_ok=True)
    todo = [(sid, p) for sid, p, _ in gen_shots()
            if not (BUILD / "frames" / (sid + ".png")).exists()]
    if limit:
        todo = todo[:limit]
    print("待生成关键帧 " + str(len(todo)) + " 张")
    for sid, prompt in todo:
        check(RE_SHOT.match(sid), "镜头号", sid)
        res = api("/v1/image/generation",
                  {"model": IMAGE_MODEL, "prompt": prompt, "aspect_ratio": "9:16", "response_format": "b64"})
        try:
            raw = base64.b64decode(res["data"][0]["image_base64"])
            check(raw[:8] == b"\x89PNG\r\n\x1a\n", "PNG头", raw[:8])
            safe_out("frames/" + sid + ".png").write_bytes(raw)
            print("  " + sid + " done")
        except (KeyError, IndexError, TypeError):
            print("  " + sid + " FAIL " + json.dumps(res, ensure_ascii=False)[:300])
        time.sleep(1)


def cmd_videos(limit):
    frames = BUILD / "frames"
    out_dir = BUILD / "shots"
    out_dir.mkdir(parents=True, exist_ok=True)
    size_cn = {"extreme_wide": "大远景", "wide": "全景", "medium": "中景",
               "medium_close": "近景", "close": "特写"}
    todo = [(sid, s) for sid, _, s in gen_shots()
            if (frames / (sid + ".png")).exists() and not (out_dir / (sid + ".mp4")).exists()]
    if limit:
        todo = todo[:limit]
    print("待生成视频 " + str(len(todo)) + " 段")
    for sid, shot in todo:
        check(RE_SHOT.match(sid), "镜头号", sid)
        b64 = base64.b64encode((frames / (sid + ".png")).read_bytes()).decode()
        motion = size_cn.get(shot["size"], shot["size"]) + "，" + shot["action"] + "，镜头缓慢运镜"
        res = api("/v1/video_generation",
                  {"model": VIDEO_MODEL, "prompt": motion[:180],
                   "first_frame_image": "data:image/png;base64," + b64})
        task_id = str(res.get("task_id", ""))
        check(task_id.isalnum(), "task_id", res.get("task_id"))
        for _ in range(60):
            time.sleep(5)
            q = api("/v1/query/video_generation?task_id=" + task_id)
            status = q.get("status")
            if status == "Success":
                file_id = str(q.get("file_id", ""))
                check(file_id.isalnum(), "file_id", q.get("file_id"))
                dl = api("/v1/files/retrieve?GroupId=" + GROUP_ID + "&file_id=" + file_id)
                url = dl.get("file", {}).get("download_url", "")
                check(url.startswith("https://") and is_safe_host(urlsplit(url).hostname or ""),
                      "下载地址", url[:120])
                mp4 = http("GET", url, timeout=300, binary=True)
                check(mp4.status_code == 200 and mp4.content[:4] == b"\x00\x00\x00",
                      "MP4内容", mp4.status_code)
                safe_out("shots/" + sid + ".mp4").write_bytes(mp4.content)
                print("  " + sid + " done")
                break
            if status in ("Fail", "InvalidInput"):
                print("  " + sid + " FAIL " + json.dumps(q, ensure_ascii=False)[:300])
                break
        else:
            print("  " + sid + " 轮询超时，重跑本命令可续传")


def run_ffmpeg(args):
    subprocess.run(["ffmpeg", "-y", "-v", "error"] + args, check=True, shell=False)


def cmd_assemble2():
    """按 animatic 时间线，把已有真实镜头替换分镜卡合成 v2（仅操作仓库内文件）。"""
    tl = json.loads((BUILD / "animatic_timeline.json").read_text())
    shots = BUILD / "shots"
    parts = BUILD / "v2_parts"
    parts.mkdir(parents=True, exist_ok=True)
    lines = []
    for s in tl["shots"]:
        check(RE_SHOT.match(s["id"]), "镜头号", s["id"])
        clip = shots / (s["id"] + ".mp4")
        card = BUILD / "animatic_frames" / (s["id"] + ".png")
        src = clip if clip.exists() else card
        out = parts / (s["id"] + ".ts")
        dur = str(s["final_dur"])
        if clip.exists():
            run_ffmpeg(["-stream_loop", "-1", "-i", str(src),
                        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
                               "fps=24,format=yuv420p,tpad=stop_mode=clone:stop_duration=180",
                        "-t", dur, "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "20", str(out)])
        else:
            run_ffmpeg(["-loop", "1", "-i", str(src), "-t", dur,
                        "-vf", "scale=1080:1920,fps=24,format=yuv420p",
                        "-c:v", "libx264", "-preset", "fast", str(out)])
        lines.append("file '" + s["id"] + ".ts'\n")
    (parts / "list.txt").write_text("".join(lines))
    run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(parts / "list.txt"),
                "-c", "copy", str(parts / "video.mp4")])
    run_ffmpeg(["-i", str(parts / "video.mp4"), "-i", str(BUILD / "animatic_v1.mp4"),
                "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k", "-shortest", str(BUILD / "final_v2.mp4")])
    done = sum(1 for s in tl["shots"] if (shots / (s["id"] + ".mp4")).exists())
    print("v2 成片 -> build/final_v2.mp4（真实镜头 " + str(done) + "/" + str(len(tl["shots"])) + " 段）")


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in {"probe", "images", "videos", "assemble2"}:
        die(__doc__)
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 0
    {"probe": cmd_probe, "images": lambda: cmd_images(limit),
     "videos": lambda: cmd_videos(limit), "assemble2": cmd_assemble2}[sys.argv[1]]()


if __name__ == "__main__":
    main()
