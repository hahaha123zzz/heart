"""确认研究大纲并取得正文。"""
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASE = "http://127.0.0.1:8000"
student = "research-43f967e3"


def call(path: str, body: dict, timeout: int = 1800) -> dict:
    request = Request(BASE + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


response = call("/api/chat", {
    "student_id": student, "account_type": "test", "session_id": "research",
    "request_id": "research-3", "message": "确认计划，开始。",
    "capability": "deep_research",
    "config": {"mode": "notes", "depth": "manual", "manual_subtopics": 1, "manual_max_iterations": 1},
})
print(json.dumps({
    "answer_status": response.get("answer_status"),
    "reply_chars": len(response.get("reply") or ""),
    "citations": len(response.get("pdf_references") or []),
    "capability": response.get("capability"),
    "clarification": bool(response.get("clarification")),
    "reply_head": (response.get("reply") or "")[:800],
}, ensure_ascii=False, indent=2))
