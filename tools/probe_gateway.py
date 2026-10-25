#!/usr/bin/env python3
"""Probe Qiniu AI gateways for usable models (SSRF-hardened, DoH direct).

Reads api keys from ZCode provider config at runtime (never prints them).
Egress policy, same as tools/minimax_pipeline.py:
  - https only
  - host allowlist: api.qnaigc.com, xapi.qiniu.io
  - local DNS gives fake-IP proxy answers (198.18.0.0/15), so resolve real
    IPs via AliDNS DoH (223.5.5.5) and map them in-process (getaddrinfo
    patch); resolved IPs must be global unicast
  - redirects disabled
Goal: resolve HANDOFF P0 -- does a gateway expose image/video generation
models besides chat-only LLMs?
"""
import ipaddress
import json
import re
import socket
import sys
import urllib.request
import urllib.error

CFG = "/Users/evander/.zcode/v2/provider_config.json"
ALLOWED_HOSTS = ("api.qnaigc.com", "xapi.qiniu.io")
RE_IP = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
_IP_CACHE = {}


def is_safe_ip(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return a.is_global and not (a.is_private or a.is_loopback
                                or a.is_link_local or a.is_reserved
                                or a.is_multicast or a.is_unspecified)


def doh_resolve(host: str) -> str:
    if not any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS):
        raise ValueError(f"DoH host not allowed: {host}")
    with urllib.request.urlopen(
            "https://223.5.5.5/resolve?name=" + host + "&type=A",
            timeout=10) as r:
        data = json.loads(r.read().decode())
    ip = [a["data"] for a in data.get("Answer", []) if a.get("type") == 1][0]
    if not (RE_IP.match(ip) and is_safe_ip(ip)):
        raise ValueError(f"DoH resolved unsafe IP for {host}: {ip}")
    return ip


_real_getaddrinfo = socket.getaddrinfo


def patched_getaddrinfo(host, port, *args, **kwargs):
    if any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS):
        if host not in _IP_CACHE:
            _IP_CACHE[host] = doh_resolve(host)
        ip = _IP_CACHE[host]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]
    return _real_getaddrinfo(host, port, *args, **kwargs)


socket.getaddrinfo = patched_getaddrinfo


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(newurl, code, "redirect blocked", headers, fp)


OPENER = urllib.request.build_opener(SafeRedirect)


def safe_open(url, headers=None, payload=None, timeout=30):
    """Open a URL after enforcing the egress policy. Returns (status, bytes)."""
    if not url.startswith("https://"):
        raise ValueError("https only")
    host = url.split("/", 3)[2]
    if not any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS):
        raise ValueError(f"host not allowed: {host}")
    data = json.dumps(payload).encode() if payload is not None else None
    hdrs = dict(headers or {})
    if data:
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, headers=hdrs, data=data,
                                 method="POST" if data else "GET")
    with OPENER.open(req, timeout=timeout) as resp:
        return resp.status, resp.read()


def load_keys():
    d = json.load(open(CFG))
    out = []
    for r in d["config"]["providerConfigRules"]["providerRules"]:
        if "七牛" in r["providerName"] or "qnaigc" in r["config"]["api"]["baseUrl"]:
            out.append((r["providerName"], r["config"]["access"]["apiKey"],
                        r["config"]["api"]["baseUrl"].rstrip("/")))
    return out


def show_err(e):
    if isinstance(e, urllib.error.HTTPError):
        print(f"  HTTP {e.code} {e.reason}: {e.read()[:200]!r}")
    else:
        print(f"  error: {e}")


def run():
    for name, key, base in load_keys():
        base = base[:-3] if base.endswith("/v1") else base
        print(f"== provider {name!r} base={base}")
        for style, extra in [
            ("openai", {"Authorization": f"Bearer {key}"}),
            ("anthropic", {"x-api-key": key, "anthropic-version": "2023-06-01"}),
        ]:
            try:
                st, body = safe_open(f"{base}/v1/models", extra)
                data = json.loads(body.decode())
                ids = [m.get("id") or m.get("name", "")
                       for m in data.get("data", data.get("models", []))]
                print(f"  [{style}] HTTP {st}, {len(ids)} models")
                interesting = [i for i in ids if any(
                    s in i.lower() for s in
                    ("minimax", "hailuo", "video", "image", "seedance",
                     "cogvideo", "wan", "doubao", "seedream", "flux",
                     "stable", "t2a", "speech", "tts", "voice"))]
                print("  gen-related:", interesting or "(none)")
                print("  all(first 40):", ids[:40])
                break
            except (urllib.error.HTTPError, urllib.error.URLError,
                    socket.timeout, OSError, ValueError) as e:
                print(f"  [{style}]", end=" ")
                show_err(e)

    keys = load_keys()
    if not keys:
        return
    _, key, base = keys[0]
    base = base[:-3] if base.endswith("/v1") else base
    auth = {"Authorization": f"Bearer {key}"}

    print(f"\n== h3-max chat test on {base}")
    try:
        st, body = safe_open(f"{base}/v1/chat/completions", auth, {
            "model": "minimax/minimax-h3-max",
            "messages": [{"role": "user", "content": "回复两个字：可用"}],
            "max_tokens": 8,
        })
        out = json.loads(body.decode())
        msg = out.get("choices", [{}])[0].get("message", {}).get("content", "")
        print(f"  HTTP {st} -> {msg!r}")
    except (urllib.error.HTTPError, urllib.error.URLError,
            socket.timeout, OSError, ValueError) as e:
        show_err(e)

    for path, payload in [
        ("/v1/images/generations",
         {"model": "minimax/image-01", "prompt": "test", "n": 1}),
        ("/v1/video/generations",
         {"model": "minimax/video-01", "prompt": "test"}),
    ]:
        print(f"\n== endpoint probe POST {path}")
        try:
            st, body = safe_open(base + path, auth, payload)
            print(f"  HTTP {st}: {body[:300]!r}")
        except (urllib.error.HTTPError, urllib.error.URLError,
                socket.timeout, OSError, ValueError) as e:
            show_err(e)

    print("\n== hackathon gateway xapi.qiniu.io reachability")
    for path in ["/v1/models", "/"]:
        try:
            st, body = safe_open("https://xapi.qiniu.io" + path)
            print(f"  GET {path} -> HTTP {st}: {body[:200]!r}")
        except (urllib.error.HTTPError, urllib.error.URLError,
                socket.timeout, OSError, ValueError) as e:
            show_err(e)


if __name__ == "__main__":
    sys.exit(run())
