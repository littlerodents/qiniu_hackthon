#!/usr/bin/env python3
"""CDP 轻量控制台：navigate / eval / shot 三个动作，配合 cdp_shot.py 使用。

用法:
  python3 tools/cdp_ctl.py <ws_url> navigate <url>
  python3 tools/cdp_ctl.py <ws_url> eval '<js表达式>'
  python3 tools/cdp_ctl.py <ws_url> click '<js元素定位表达式>'   # 返回元素的 click()
  python3 tools/cdp_ctl.py <ws_url> shot <png路径> [wait_sec]
输出路径仅允许本项目 build/ 目录或 /tmp。
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

    def call(self, method, params=None, timeout=25):
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


def page_text(cdp, limit=800):
    res = cdp.call("Runtime.evaluate", {
        "expression": (
            "JSON.stringify({url: location.href, title: document.title, ready: document.readyState, "
            f"text: document.body ? document.body.innerText.replace(/\\s+/g,' ').slice(0, {limit}) : ''}})"
        ),
        "returnByValue": True,
    })
    return json.loads(res["result"]["value"])


def main():
    ws_url, action = sys.argv[1], sys.argv[2]
    cdp = CDP(ws_url)
    try:
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        if action == "navigate":
            cdp.call("Page.navigate", {"url": sys.argv[3]})
            time.sleep(3)
            print(json.dumps(page_text(cdp), ensure_ascii=False, indent=2))
        elif action == "eval":
            res = cdp.call("Runtime.evaluate", {
                "expression": sys.argv[3], "returnByValue": True, "awaitPromise": True,
            })
            print(json.dumps(res.get("result", res), ensure_ascii=False, default=str)[:4000])
        elif action == "click":
            js = f"(() => {{ const el = {sys.argv[3]}; if (!el) return 'NOT_FOUND'; el.click(); return 'CLICKED ' + (el.innerText||el.tagName).slice(0,40); }})()"
            res = cdp.call("Runtime.evaluate", {"expression": js, "returnByValue": True})
            print(res["result"]["value"])
            time.sleep(4)
            print(json.dumps(page_text(cdp), ensure_ascii=False, indent=2))
        elif action == "shot":
            out = safe_output(sys.argv[3])
            wait = float(sys.argv[4]) if len(sys.argv) > 4 else 2.0
            time.sleep(wait)
            shot = cdp.call("Page.captureScreenshot", {"format": "png"})
            out.write_bytes(base64.b64decode(shot["data"]))
            print(f"screenshot -> {out}")
        else:
            raise SystemExit(f"unknown action: {action}")
    finally:
        cdp.close()


if __name__ == "__main__":
    main()
