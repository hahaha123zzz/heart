"""8000 服务验收：健康、教材问答、引用、记忆卡片与 mem0 行。"""
from __future__ import annotations

import json
import os
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


def _call(path: str, body: dict | None = None) -> dict:
    request = Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                      headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=600) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    student = "accept-" + uuid4().hex[:10]
    report = {"student": student, "questions": []}
    health = _call("/health")
    report["health"] = {"fixed_book": health.get("fixed_book"), "course": health.get("course_id")}
    _call("/api/accounts/test", {"student_id": student, "ttl_hours": 2})
    questions = [
        "什么是自变量？",
        "自变量和因变量有什么区别？",
        "第一章的实验程序和第二章的自变量控制有什么联系？",
    ]
    for index, question in enumerate(questions, 1):
        result = _call("/api/chat", {
            "student_id": student, "account_type": "test", "session_id": "accept",
            "request_id": f"accept-{index}", "message": question,
        })
        citations = result.get("pdf_references") or []
        report["questions"].append({
            "question": question,
            "answer_status": result.get("answer_status"),
            "reply_chars": len(result.get("reply") or ""),
            "citations": len(citations),
            "citation_documents": sorted({(c.get("document_id") or c.get("evidence", {}).get("document_id") or "")
                                          for c in citations} - {""}),
        })
    import psycopg

    with psycopg.connect(os.environ["COURSE_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")) as conn:
        report["db"] = {
            "conversations": conn.execute("select count(*) from conversations where student_id=%s", (student,)).fetchone()[0],
            "memory_cards": conn.execute("select count(*) from memory_documents where student_id=%s", (student,)).fetchone()[0],
            "mem0_rows": conn.execute("select count(*) from student_memory where payload->>'user_id'=%s", (student,)).fetchone()[0],
        }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
