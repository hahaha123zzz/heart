"""划选、图题、研究的 HTTP 验收。"""
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

from knowledge.pdf_reader import PDFSelection, document_for_chapter

BASE = "http://127.0.0.1:8000"


def call(path: str, body: dict | None = None, timeout: int = 900) -> dict:
    request = Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                      headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    student = "accept-media-" + uuid4().hex[:8]
    call("/api/accounts/test", {"student_id": student, "ttl_hours": 2})
    record = document_for_chapter(2)
    section = record["sections"][1]
    rect = section["rect"] | {"x1": .14, "x2": .84, "y2": min(.95, section["rect"]["y2"] + .12)}
    selection = PDFSelection(document_id=record["document_id"], version=record["version"],
                             kind="text", rects=[rect])
    report = {"student": student, "selection": None, "figure": None, "research": None}

    selected = call("/api/chat", {
        "student_id": student, "account_type": "test", "session_id": "media", "request_id": "media-selection",
        "message": "请解释我选中的这段内容，并引用本次选区。",
        "selection": selection.model_dump(),
    })
    first = ((selected.get("pdf_references") or [{}])[0].get("selection_ref") or {})
    report["selection"] = {
        "answer_status": selected.get("answer_status"),
        "document": first.get("document_id"),
        "version": first.get("version"),
        "citations": len(selected.get("pdf_references") or []),
        "reply_chars": len(selected.get("reply") or ""),
    }

    figure = call("/api/chat", {
        "student_id": student, "account_type": "test", "session_id": "media", "request_id": "media-figure",
        "message": "图1-4讲的是什么？请依据教材原图说明。",
    })
    images = [item.get("id") for item in (figure.get("image_refs") or []) if isinstance(item, dict)]
    report["figure"] = {
        "answer_status": figure.get("answer_status"),
        "image_refs": images,
        "mentions_figure": "图1-4" in (figure.get("reply") or ""),
        "citations": len(figure.get("pdf_references") or []),
    }

    research = call("/api/chat", {
        "student_id": student, "account_type": "test", "session_id": "media", "request_id": "media-research",
        "message": "帮我研究自变量控制这个子主题。",
        "capability": "deep_research",
        "config": {"mode": "notes", "depth": "manual", "manual_subtopics": 1, "manual_max_iterations": 1},
    })
    report["research"] = {
        "answer_status": research.get("answer_status"),
        "citations": len(research.get("pdf_references") or []),
        "reply_chars": len(research.get("reply") or ""),
        "has_clarify": bool(research.get("clarification")),
    }

    import psycopg

    with psycopg.connect(os.environ["COURSE_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")) as conn:
        report["db_figure_ids"] = conn.execute(
            "select figure_ids from figure_citations where conversation_id in "
            "(select id from conversations where student_id=%s)", (student,)).fetchall()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
