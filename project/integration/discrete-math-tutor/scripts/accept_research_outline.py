"""按已确认大纲运行研究，取得正文。"""
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASE = "http://127.0.0.1:8000"
student = "research-43f967e3"
outline = [{
    "title": "自变量控制：概念、方法与实施要点",
    "overview": "聚焦实验研究中自变量控制的核心问题，涵盖其定义与目的、常见控制方法（如操纵、恒定、平衡、随机化等），以及实施中的关键要点与常见偏差。",
}]


def call(path: str, body: dict, timeout: int = 1800) -> dict:
    request = Request(BASE + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


response = call("/api/chat", {
    "student_id": student, "account_type": "test", "session_id": "research",
    "request_id": "research-14", "message": "请按已确认的大纲开始研究自变量控制这个子主题。",
    "capability": "deep_research",
    "knowledge_bases": ["experimental-psychology-3-lightrag"],
    "config": {"mode": "notes", "depth": "manual", "manual_subtopics": 1,
               "manual_max_iterations": 1, "confirmed_outline": outline},
})
print(json.dumps({
    "answer_status": response.get("answer_status"),
    "reply_chars": len(response.get("reply") or ""),
    "citations": len(response.get("pdf_references") or []),
    "capability": response.get("capability"),
    "clarification": bool(response.get("clarification")),
    "reply_head": (response.get("reply") or "")[:800],
}, ensure_ascii=False, indent=2))
