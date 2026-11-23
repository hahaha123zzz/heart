"""复现“没看懂，用可视化解释”回合，查看能力与门禁。"""
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASE = "http://127.0.0.1:8000"
student = "viz-" + uuid4().hex[:8]


def call(path: str, body: dict, timeout: int = 900) -> dict:
    request = Request(BASE + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


call("/api/accounts/test", {"student_id": student, "ttl_hours": 2})
first = call("/api/chat", {"student_id": student, "account_type": "test", "session_id": "viz",
                           "request_id": "viz-1", "message": "什么是额外变量？"})
second = call("/api/chat", {"student_id": student, "account_type": "test", "session_id": "viz",
                            "request_id": "viz-2", "message": "没看懂，用可视化给我解释一下。"})
print(json.dumps({
    "student": student,
    "first": {"status": first.get("answer_status"), "capability": first.get("capability")},
    "second": {"status": second.get("answer_status"), "capability": second.get("capability"),
               "reply_chars": len(second.get("reply") or ""), "citations": len(second.get("pdf_references") or []),
               "has_visual": bool(second.get("native_presentation") or second.get("image_refs")),
               "reply_head": (second.get("reply") or "")[:200]},
}, ensure_ascii=False, indent=2))
