"""验收：两个学生账号的会话隔离。

用法：python scripts/check_account_isolation.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import requests
import websockets

BASE = "http://127.0.0.1:3000"
WS = "ws://127.0.0.1:3000/ws"
CREDS = Path(__file__).resolve().parents[1] / ".runtime" / "vendor-accounts.txt"


def password(username: str) -> str:
    lines = [l for l in CREDS.read_text(encoding="utf-8").splitlines() if l.startswith(f"{username}\t")]
    return lines[-1].split("\t", 1)[1]


def login(username: str) -> requests.Session:
    session = requests.Session()
    response = session.post(f"{BASE}/api/auth/login",
                            json={"username": username, "password": password(username)}, timeout=30)
    response.raise_for_status()
    return session


async def start_turn(cookie: str) -> str:
    headers = {"Cookie": cookie, "Origin": BASE}
    async with websockets.connect(WS, additional_headers=headers,
                                  open_timeout=20, max_size=8_000_000) as ws:
        await ws.send(json.dumps({"type": "start_turn", "protocol_version": "2.0",
                                  "content": "隔离检查：只回一句“收到”。"}))
        while True:
            message = json.loads(await asyncio.wait_for(ws.recv(), timeout=180))
            kind = message.get("type")
            if kind == "session":
                session_id = message.get("session_id") or (message.get("metadata") or {}).get("session_id")
                if session_id:
                    return str(session_id)
            if kind in ("done", "error", "protocol_error"):
                raise RuntimeError(f"回合未产生 session：{kind}")


def sessions(session: requests.Session) -> list[str]:
    payload = session.get(f"{BASE}/api/sessions", timeout=30).json()
    return [str(item.get("session_id") or item.get("id")) for item in payload.get("sessions") or []]


def main() -> None:
    one = login("student01")
    two = login("student02")
    cookie = "; ".join(f"{k}={v}" for k, v in one.cookies.get_dict().items())
    session_id = asyncio.run(start_turn(cookie))
    one_ids, two_ids = sessions(one), sessions(two)
    print(f"created={session_id}")
    print(f"student01 sees it: {session_id in one_ids} (n={len(one_ids)})")
    print(f"student02 sees it: {session_id in two_ids} (n={len(two_ids)})")
    leak = two.get(f"{BASE}/api/sessions/{session_id}", timeout=30)
    print(f"student02 GET session -> {leak.status_code}")
    ok = (session_id in one_ids) and (session_id not in two_ids) and leak.status_code in (403, 404)
    print("ISOLATION_OK" if ok else "ISOLATION_FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
