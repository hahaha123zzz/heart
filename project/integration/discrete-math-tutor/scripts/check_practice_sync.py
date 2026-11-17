"""验收：在厂家练习里作答一题（review），供 evidence 同步使用。"""
from __future__ import annotations

import uuid
from pathlib import Path

import requests

BASE = "http://127.0.0.1:3000"
CREDS = Path(__file__).resolve().parents[1] / ".runtime" / "vendor-accounts.txt"


def password(username: str) -> str:
    lines = [l for l in CREDS.read_text(encoding="utf-8").splitlines()
             if l.startswith(f"{username}\t")]
    return lines[-1].split("\t", 1)[1]


def main() -> None:
    session = requests.Session()
    session.post(f"{BASE}/api/auth/login",
                 json={"username": "student01", "password": password("student01")},
                 timeout=30).raise_for_status()
    queue = session.get(f"{BASE}/api/question-notebook/practice/queue", timeout=30).json()
    item = queue[0]
    entry = item["entry"]
    version = int((item.get("state") or {}).get("version") or 0)
    answer = entry["correct_answer"]
    request_id = uuid.uuid4().hex
    response = session.post(
        f"{BASE}/api/question-notebook/practice/questions/{entry['id']}/review",
        json={"answer": answer, "request_id": request_id, "version": version,
              "rating": "good"}, timeout=60)
    response.raise_for_status()
    body = response.json()
    print(f"entry={entry['id']} kc_category={[c['name'] for c in entry.get('categories') or []]}")
    print(f"review={body}")
    print(f"entry_id={entry['id']} answer={answer} request_id={request_id}")


if __name__ == "__main__":
    main()
