"""验收：经 V/web 代理建 WS，登录态发一条 start_turn，看事件与 done。

用法（从 H 运行，用 .venv-deeptutor）：
  python scripts/check_vendor_ws.py
凭据从 .runtime/vendor-accounts.txt 读取，不打印密码。
"""
from __future__ import annotations

import asyncio
import json
import sys
import urllib.request
from pathlib import Path

import websockets

BASE = "http://127.0.0.1:3000"
WS = "ws://127.0.0.1:3000/ws"
CREDS = Path(__file__).resolve().parents[1] / ".runtime" / "vendor-accounts.txt"
PROMPT = "用一句话说明什么是自变量"


def current_password(username: str = "student01") -> str:
    lines = [l for l in CREDS.read_text(encoding="utf-8").splitlines() if l.startswith(f"{username}\t")]
    return lines[-1].split("\t", 1)[1]


def login(username: str, password: str) -> str:
    body = json.dumps({"username": username, "password": password}).encode()
    request = urllib.request.Request(
        BASE + "/api/auth/login", data=body,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        cookies = response.headers.get_all("Set-Cookie") or []
    for item in cookies:
        if item.startswith("dt_token="):
            return item.split(";", 1)[0]
    raise RuntimeError("登录未返回 dt_token")


async def run() -> int:
    cookie = login("student01", current_password())
    try:
        import websockets
        connect = websockets.connect
    except AttributeError:
        raise SystemExit("websockets 不可用")
    extra = {"Cookie": cookie, "Origin": BASE}
    try:
        ws = await connect(WS, additional_headers=extra, open_timeout=20, max_size=8_000_000)
    except TypeError:
        ws = await connect(WS, extra_headers=extra, open_timeout=20, max_size=8_000_000)
    types: list[str] = []
    content_chars = 0
    async with ws:
        await ws.send(json.dumps({"type": "start_turn", "protocol_version": "2.0",
                                  "client_submission_id": "sub-1", "content": PROMPT}))
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=180)
            message = json.loads(raw)
            kind = message.get("type")
            types.append(kind)
            if kind == "content":
                content_chars += len(message.get("content") or "")
            if kind == "protocol_error":
                print("protocol_error:", message.get("error_code"), message.get("message"))
                return 2
            if kind == "error":
                print("error:", message.get("message") or message.get("error_code"))
                return 2
            if kind == "done":
                body = message.get("metadata") or {}
                print("done:", json.dumps(body, ensure_ascii=False)[:200])
                break
    print("events:", len(types), "types:", sorted(set(types)))
    print("content_chars:", content_chars)
    return 0 if content_chars > 0 else 3


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
