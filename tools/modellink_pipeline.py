#!/usr/bin/env python3
"""ModelLink 网关（api.qnaigc.com）产线适配：
  images  关键帧：POST /bypass/openai/v1/images/generations（gpt-image-2，Bearer）
  videos  图生视频：POST /queue/minimax/h3-max/image-to-video（FAL 格式，Key 认证）
          轮询 GET /queue/minimax/h3-max/requests/{rid}/status（202 未完 / 200 完，
          FAILED 也会标 COMPLETED，须检查 detail 为 null）
  probe   认证/路由/模型清单零成本探测
凭据只读环境变量 MINIMAX_API_KEY。产物：build/frames/<id>.png、build/shots/<id>.mp4，
随后用 `python3 tools/minimax_pipeline.py assemble2` 合成 final_v2.mp4。
安全骨架与 minimax_pipeline.py 一致：仅 https + 域名白名单 + DoH 真实 IP 直连
（绕 fake-IP 代理）+ 私网 IP 阻断 + 禁重定向；request_id 白名单校验后才能进 URL；
文件写入仅限 build/。
"""
import base64
import ipaddress
import json
import math
import os
import re
import socket
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"

API_HOST_RAW = os.environ.get("MINIMAX_API_HOST", "api.qnaigc.com")
API_KEY = os.environ.get("MINIMAX_API_KEY", "")
IMAGE_MODEL = os.environ.get("MM_IMAGE_MODEL", "openai/gpt-image-2")

RE_IP = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
RE_HOST = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)*$")
RE_SHOT = re.compile(r"^S\d-\d{2}$")
RE_RID = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
ALLOWED_HOST_SUFFIXES = (".qnaigc.com", ".qiniu.io", ".qiniu.com",
                         ".qnlinking.com", ".qiniucdn.com",
                         ".minimax.chat", ".minimaxi.com")
VIDEO_BASE = "/queue/minimax/h3-max"
DOWNLOAD_SUFFIXES = (".qiniucdn.com", ".qiniu.com", ".qnlinking.com",
                     ".qnaigc.com", ".minimax.chat", ".minimaxi.com")
ALLOWED_DIRS = (str(BUILD.resolve()),)


def die(msg):
    raise SystemExit("[modellink] " + msg)


def check(cond, label, value):
    if not cond:
        die(label + " 校验失败: " + str(value)[:120])
    return value


def validated_host(raw: str) -> str:
    h = raw.strip().lower()
    if not (RE_HOST.match(h) and h.endswith(ALLOWED_HOST_SUFFIXES)):
        die("API 主机名白名单校验失败: " + h)
    return h


API_HOST = validated_host(API_HOST_RAW)


def is_safe_ip(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (a.is_private or a.is_loopback or a.is_link_local or a.is_reserved
                or a.is_multicast or a.is_unspecified)


def is_safe_host(host) -> bool:
    return bool(host) and bool(RE_HOST.match(host)) and host.endswith(ALLOWED_HOST_SUFFIXES)


def doh_resolve(host: str) -> str:
    """AliDNS DoH 解析真实 IP（仅类型 A 记录），绕开本机 fake-IP 代理。"""
    if not (RE_HOST.match(host) and is_safe_host(host)):
        die("DoH 域名白名单", host)
    with urllib.request.urlopen(
            "https://223.5.5.5/resolve?name=" + host + "&type=A",
            timeout=10) as r:
        data = json.loads(r.read().decode())
    for ans in data.get("Answer", []):
        if ans.get("type") == 1:
            ip = ans["data"]
            if RE_IP.match(ip) and is_safe_ip(ip):
                return ip
    die("DoH 无可用 A 记录", host)


_IP_CACHE = {}
_real_getaddrinfo = socket.getaddrinfo


def patched_getaddrinfo(host, port, *args, **kwargs):
    if is_safe_host(host):
        if host not in _IP_CACHE:
            _IP_CACHE[host] = doh_resolve(host)
        ip = _IP_CACHE[host]
        check(is_safe_ip(ip), "解析IP边界", ip)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]
    return _real_getaddrinfo(host, port, *args, **kwargs)


socket.getaddrinfo = patched_getaddrinfo


def http(method: str, url: str, payload=None, auth="bearer", timeout=120,
         binary=False, host_suffixes=None):
    """统一出网：仅 https + 域名后缀白名单 + IP 边界 + 禁重定向。"""
    check(method in ("GET", "POST"), "HTTP方法", method)
    from urllib.parse import urlsplit
    parts = urlsplit(url)
    check(parts.scheme == "https", "协议必须https", url)
    suffixes = host_suffixes or ALLOWED_HOST_SUFFIXES
    host = parts.hostname or ""
    check(RE_HOST.match(host) and host.endswith(suffixes), "请求域名", url)
    ip = patched_getaddrinfo(host, 443, socket.AF_INET)[0][4][0]
    check(is_safe_ip(ip), "解析IP边界", ip)
    if not API_KEY:
        die("缺少 MINIMAX_API_KEY 环境变量（凭据不入库，只走环境变量）")
    token = "Key " + API_KEY if auth == "key" else "Bearer " + API_KEY
    ses = requests.Session()
    ses.trust_env = False
    r = ses.request(method, url, json=payload, timeout=timeout,
                    allow_redirects=False,
                    headers={"Authorization": token,
                             "Content-Type": "application/json"})
    if binary:
        return r
    try:
        return r.json()
    except ValueError:
        die("非 JSON 响应 HTTP " + str(r.status_code) + ": " + r.text[:300])


def gen_jobs():
    """从分镜表与提示词清单取得待生成镜头 [(id, prompt_text, final_dur)]。"""
    board = json.loads((ROOT / "assets/storyboard/ep1_storyboard.json")
                       .read_text(encoding="utf-8"))
    manifest = json.loads((BUILD / "prompts/manifest.json")
                          .read_text(encoding="utf-8"))["manifest"]
    prompts = {m["id"]: m for m in manifest if m["type"] == "gen"}
    tl = json.loads((BUILD / "animatic_timeline.json").read_text())
    durs = {s["id"]: s["final_dur"] for s in tl["shots"]}
    out = []
    for s in board["shots"]:
        if s["id"] in prompts:
            text = (ROOT / prompts[s["id"]]["prompt_file"]).read_text().strip()
            out.append((s["id"], text, durs.get(s["id"], s.get("dur", 5))))
    return out


def safe_out(rel: str) -> Path:
    p = (BUILD / rel).resolve()
    check(str(p).startswith(ALLOWED_DIRS), "输出路径越界", rel)
    return p


# ---------------- 子命令 ----------------

def cmd_probe():
    print("host=" + API_HOST + " image=" + IMAGE_MODEL + " video=queue/minimax-h3-max")
    print("连通性(DoH+直连):", doh_resolve(API_HOST))
    data = http("GET", "https://" + API_HOST + "/v1/models")
    ids = [m.get("id", "") for m in data.get("data", [])]
    print("models:", len(ids), "（含 minimax 系:",
          [i for i in ids if "minimax" in i.lower()][:6], "）")
    r = http("GET", "https://" + API_HOST + VIDEO_BASE
             + "/requests/probe-nonexistent00/status", binary=True)
    code = r.status_code
    print("queue 路由: HTTP", code, "（404/400=路由与认证正常，401=凭据问题）")


def gen_image(shot_id, prompt):
    out = safe_out("frames/" + shot_id + ".png")
    if out.exists():
        print("skip", shot_id)
        return
    data = http("POST", "https://" + API_HOST
                + "/bypass/openai/v1/images/generations", {
                    "model": IMAGE_MODEL,
                    "prompt": prompt[:30000],
                    "size": "1024x1536",
                    "n": 1,
                    "quality": "high",
                }, timeout=360)
    items = data.get("data") or []
    check(items, "图像响应无 data", json.dumps(data)[:200])
    b64 = items[0].get("b64_json")
    url = items[0].get("url")
    print("  响应字段:", list(items[0].keys()), "url:", (url or "无")[:100])
    out.parent.mkdir(parents=True, exist_ok=True)
    if url and url.startswith("https://"):
        (out.with_suffix(".url")).write_text(url)
    if b64:
        out.write_bytes(base64.b64decode(b64))
        print("image ok", shot_id, out.stat().st_size, "bytes")
        return
    if url and url.startswith("https://"):
        download_image(url, out)
        return
    die("响应缺 b64_json 与可用 url", list(items[0].keys()))


def download_image(url: str, dest: Path):
    check(url.startswith("https://"), "图像URL协议", url[:60])
    host = url.split("/", 3)[2]
    check(RE_HOST.match(host) and host.endswith(DOWNLOAD_SUFFIXES),
          "图像URL域名白名单", url[:80])
    r = http("GET", url, binary=True, timeout=300,
             host_suffixes=DOWNLOAD_SUFFIXES)
    check(r.status_code == 200, "图像下载状态", r.status_code)
    dest.write_bytes(r.content)
    print("image ok(via url)", dest.name, dest.stat().st_size, "bytes")


def cmd_images(limit):
    jobs = gen_jobs()
    todo = jobs[:limit] if limit else jobs
    for shot_id, prompt, _ in todo:
        gen_image(shot_id, prompt)


def download(url: str, dest: Path):
    check(url.startswith("https://"), "下载协议", url[:60])
    host = url.split("/", 3)[2]
    check(RE_HOST.match(host) and host.endswith(DOWNLOAD_SUFFIXES),
          "下载域名白名单", url[:80])
    r = http("GET", url, binary=True, timeout=300, host_suffixes=DOWNLOAD_SUFFIXES)
    check(r.status_code == 200, "下载状态", r.status_code)
    dest.write_bytes(r.content)


def submit(shot_id, prompt, dur):
    """入队一个镜头：优先图生视频（需 frames/<id>.url 公网图），否则文生视频。"""
    v_dur = max(5, min(15, math.ceil(dur)))
    frame_url = None
    url_file = safe_out("frames/" + shot_id + ".url")
    if url_file.exists():
        candidate = url_file.read_text().strip()
        if candidate.startswith("https://"):
            frame_url = candidate
    if frame_url:
        path, extra = "/image-to-video", {"image_url": frame_url}
    else:
        path, extra = "/text-to-video", {}
    body = None
    for attempt in range(4):
        body = http("POST", "https://" + API_HOST + VIDEO_BASE + path, {
            "prompt": prompt[:1500],
            "duration": v_dur,
            "resolution": "768P",
            "aspect_ratio": "9:16",
            "prompt_expansion_mode": "balanced",
            **extra,
        })
        rid = body.get("request_id", "")
        if RE_RID.match(rid):
            mode = "i2v" if frame_url else "t2v"
            print("queued", shot_id, mode, "dur", v_dur, "rid", rid[:24])
            return rid
        print("  ", shot_id, "提交失败(第%d次):" % (attempt + 1),
              json.dumps(body, ensure_ascii=False)[:200])
        time.sleep(15 * (attempt + 1))
    die("提交重试耗尽 " + shot_id + ": "
        + json.dumps(body, ensure_ascii=False)[:300])


def wait_video(shot_id, rid, budget=1500):
    """轮询到完成；FAILED 会伪装成 COMPLETED，以 detail 为准。"""
    deadline = time.time() + budget
    while time.time() < deadline:
        time.sleep(12)
        st = http("GET", "https://" + API_HOST + VIDEO_BASE
                  + "/requests/" + rid + "/status")
        status = st.get("status")
        if status in ("COMPLETED", "FAILED"):
            detail = st.get("detail")
            check(detail is None, "任务失败 detail",
                  json.dumps(detail, ensure_ascii=False)[:300])
            url = (((st.get("result") or {}).get("video")) or {}).get("url")
            if not url:
                r = http("GET", "https://" + API_HOST + VIDEO_BASE
                         + "/requests/" + rid)
                url = (((r.get("result") or {}).get("video")) or {}).get("url")
            check(url, "结果缺 video.url", json.dumps(st)[:200])
            return url
        if status == "IN_QUEUE" and (st.get("queue_position") or 0) > 0:
            print("  ", shot_id, status, "pos", st.get("queue_position"))
    die(shot_id + " 轮询超时 rid=" + rid)


def cmd_videos(limit):
    jobs = gen_jobs()
    todo = [(i, p, d) for i, p, d in (jobs[:limit] if limit else jobs)
            if not safe_out("shots/" + i + ".mp4").exists()]
    est = sum(max(5, min(15, math.ceil(d))) for _, _, d in todo)
    print("待生成", len(todo), "镜，预计输出秒数（计费）≈", est, "s")
    # 两阶段：全部入队（服务端并行），再逐个轮询下载；jobs.json 支持断点续跑
    state = safe_out("video_jobs.json")
    rids = {}
    if state.exists():
        try:
            rids = {k: v for k, v in json.loads(state.read_text()).items()
                    if not safe_out("shots/" + k + ".mp4").exists()}
        except ValueError:
            rids = {}
    for shot_id, prompt, dur in todo:
        if shot_id in rids:
            continue
        rids[shot_id] = submit(shot_id, prompt, dur)
        time.sleep(2)
        state.write_text(json.dumps(rids, ensure_ascii=False, indent=1))
    for shot_id, rid in rids.items():
        url = wait_video(shot_id, rid)
        out = safe_out("shots/" + shot_id + ".mp4")
        out.parent.mkdir(parents=True, exist_ok=True)
        download(url, out)
        print("video ok", shot_id, out.stat().st_size, "bytes")


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("probe", "images", "videos"):
        die("用法: modellink_pipeline.py probe | images [--limit N] | videos [--limit N]")
    cmd = sys.argv[1]
    limit = 0
    if "--limit" in sys.argv:
        i = sys.argv.index("--limit")
        check(i + 1 < len(sys.argv) and sys.argv[i + 1].isdigit(),
              "limit 数字", sys.argv[i + 1] if i + 1 < len(sys.argv) else "(缺)")
        limit = int(sys.argv[i + 1])
    if cmd == "probe":
        cmd_probe()
    elif cmd == "images":
        cmd_images(limit)
    else:
        cmd_videos(limit)


if __name__ == "__main__":
    main()
