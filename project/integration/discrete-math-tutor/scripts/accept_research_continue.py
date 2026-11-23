"""提交研究澄清答案，验证研究报告正文。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import psycopg

BASE = "http://127.0.0.1:8000"
STUDENT = "accept-media-e2e90570"


def call(path: str, body: dict, timeout: int = 1800) -> dict:
    request = Request(BASE + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


url = os.environ["COURSE_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
call("/api/accounts/test", {"student_id": STUDENT, "ttl_hours": 2})
with psycopg.connect(url) as conn:
    row = conn.execute(
        "select id, revision, result from learning_tasks where student_id=%s and status='awaiting_clarification' "
        "order by id desc limit 1", (STUDENT,)
    ).fetchone()
if not row:
    raise SystemExit("no awaiting research task")
task_id, revision, result = row
clarification = result.get("clarification") or {}
questions = (clarification.get("ask_user") or {}).get("questions") or clarification.get("questions") or []
answers = []
for question in questions:
    options = question.get("options") or []
    label = options[0]["label"] if options else "由你决定"
    answers.append({"questionId": question["id"], "text": label})
message = "补充说明：" + "；".join(f"{a['questionId']}={a['text']}" for a in answers)
print("task", task_id, "revision", revision, "answers", answers)
response = call("/api/chat", {
    "student_id": STUDENT, "account_type": "test", "session_id": "media",
    "request_id": "research-continue-1", "message": message,
    "task_id": task_id, "task_revision": revision, "answers": answers,
})
print(json.dumps({
    "answer_status": response.get("answer_status"),
    "reply_chars": len(response.get("reply") or ""),
    "citations": len(response.get("pdf_references") or []),
    "clarification": bool(response.get("clarification")),
    "capability": response.get("capability"),
    "reply_head": (response.get("reply") or "")[:400],
}, ensure_ascii=False, indent=2))
