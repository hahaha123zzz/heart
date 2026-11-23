"""一次性研究验收：发起 → 回答澄清 → 取得正文。"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

BASE = "http://127.0.0.1:8000"


def call(path: str, body: dict, timeout: int = 1800) -> dict:
    request = Request(BASE + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


student = "research-" + uuid4().hex[:8]
call("/api/accounts/test", {"student_id": student, "ttl_hours": 4})
first = call("/api/chat", {
    "student_id": student, "account_type": "test", "session_id": "research",
    "request_id": "research-1", "message": "帮我研究自变量控制这个子主题。",
    "capability": "deep_research",
    "config": {"mode": "notes", "depth": "manual", "manual_subtopics": 1, "manual_max_iterations": 1},
})
print("first", first.get("answer_status"), "task", first.get("task_id"), first.get("task_revision"))
clarification = first.get("clarification") or {}
questions = (clarification.get("ask_user") or {}).get("questions") or clarification.get("questions") or []
if first.get("answer_status") == "awaiting_clarification" and questions:
    answers = []
    for question in questions:
        options = question.get("options") or []
        answers.append({"questionId": question["id"], "text": options[0]["label"] if options else "由你决定"})
    message = "补充说明：" + "；".join(f"{a['questionId']}={a['text']}" for a in answers)
    second = call("/api/chat", {
        "student_id": student, "account_type": "test", "session_id": "research",
        "request_id": "research-2", "message": message,
        "task_id": first["task_id"], "task_revision": first["task_revision"], "answers": answers,
    })
else:
    second = first
print(json.dumps({
    "student": student,
    "answer_status": second.get("answer_status"),
    "reply_chars": len(second.get("reply") or ""),
    "citations": len(second.get("pdf_references") or []),
    "clarification": bool(second.get("clarification")),
    "capability": second.get("capability"),
    "reply_head": (second.get("reply") or "")[:600],
}, ensure_ascii=False, indent=2))
