"""划选验收：使用章节原始矩形，核对返回引用身份。"""
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

from knowledge.pdf_reader import PDFSelection, document_for_chapter, resolve_selection

BASE = "http://127.0.0.1:8000"


def call(path: str, body: dict) -> dict:
    request = Request(BASE + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=600) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    student = "accept-sel-" + uuid4().hex[:8]
    call("/api/accounts/test", {"student_id": student, "ttl_hours": 2})
    record = document_for_chapter(2)
    section = record["sections"][1]
    selection = PDFSelection(document_id=record["document_id"], version=record["version"],
                             kind="text", rects=[section["rect"]])
    resolved = resolve_selection(selection)
    result = call("/api/chat", {
        "student_id": student, "account_type": "test", "session_id": "sel", "request_id": "sel-1",
        "message": "请解释我选中的“自变量及控制”这段，并引用本次选区。",
        "selection": selection.model_dump(),
    })
    citations = result.get("pdf_references") or []
    def _selection(item):
        return item.get("selection_ref") or {}
    summary = [{
        "document_id": _selection(item).get("document_id") or item.get("document_id"),
        "version": _selection(item).get("version") or item.get("version"),
        "page": ((_selection(item).get("rects") or [{}])[0]).get("page"),
        "label": item.get("label"),
        "section_id": _selection(item).get("section_id"),
        "rects": len(_selection(item).get("rects") or []),
    } for item in citations]
    report = {
        "student": student,
        "selected": {"document_id": record["document_id"], "version": record["version"],
                     "section": section["title"], "resolved_chars": len(resolved.get("text") or "")},
        "answer_status": result.get("answer_status"),
        "reply_chars": len(result.get("reply") or ""),
        "citations": summary,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    assert report["answer_status"] == "answered" and report["selected"]["resolved_chars"] > 0
    assert any(item["document_id"] == record["document_id"] and item["version"] == record["version"]
               for item in summary)


if __name__ == "__main__":
    main()
