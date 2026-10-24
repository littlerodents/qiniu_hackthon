#!/usr/bin/env python3
"""CDP 页面观察工具：连接 Chrome DevTools 协议，输出页面状态文本 + 整页截图。

用法: python3 tools/cdp_shot.py <ws_url> <out_png> [wait_sec]
依赖: websocket-client（本机 anaconda python 自带）
输出路径仅允许写入本项目 build/ 目录或 /tmp（防止路径穿越误写）。
"""
import base64
import json
import sys
import time
from pathlib import Path

import websocket

ALLOWED_ROOTS = (Path("/Users/evander/Labs/langya-xcanvas/build").resolve(), Path("/tmp").resolve())


def safe_output(path_str: str) -> Path:
    p = Path(path_str).resolve()
    if not any(str(p).startswith(str(r)) for r in ALLOWED_ROOTS):
        raise ValueError(f"output path must stay under {ALLOWED_ROOTS}: {p}")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


class CDP:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=15, suppress_origin=True)
        self.seq = 0

    def call(self, method, params=None, timeout=20):
        self.seq += 1
        mid = self.seq
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})
        raise TimeoutError(method)

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def main():
    ws_url, out_png = sys.argv[1], sys.argv[2]
    wait_sec = float(sys.argv[3]) if len(sys.argv) > 3 else 5.0
    nav_url = sys.argv[4] if len(sys.argv) > 4 else None
    out = safe_output(out_png)
    cdp = CDP(ws_url)
    try:
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        if nav_url:
            cdp.call("Page.navigate", {"url": nav_url})
            time.sleep(3.0)
        time.sleep(wait_sec)
        res = cdp.call("Runtime.evaluate", {
            "expression": (
                "JSON.stringify({url: location.href, title: document.title, ready: document.readyState, "
                "text: document.body ? document.body.innerText.replace(/\\s+/g,' ').slice(0, 600) : ''})"
            ),
            "returnByValue": True,
        })
        info = json.loads(res["result"]["value"])
        print(json.dumps(info, ensure_ascii=False, indent=2))
        shot = cdp.call("Page.captureScreenshot", {"format": "png"})
        out.write_bytes(base64.b64decode(shot["data"]))
        print(f"screenshot -> {out}")
    finally:
        cdp.close()


if __name__ == "__main__":
    main()
