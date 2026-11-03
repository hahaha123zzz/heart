"""Isolated live acceptance for chapter overview; real model, temp DB, no service restart."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def configure(key_file: Path, output: Path, model: str) -> None:
    from dotenv import dotenv_values
    values = dotenv_values(key_file)
    raw = key_file.read_text(encoding="utf-8-sig").strip().strip("\"'")
    key = values.get("DEEPSEEK_API_KEY") or values.get("OPENAI_API_KEY")
    if not key:
        key = raw if raw.startswith("sk-") and not any(c.isspace() for c in raw) else next(
            (v.strip().strip("\"'") for v in values.values()
             if isinstance(v, str) and v.strip().strip("\"'").startswith("sk-")), None)
    if not key:
        raise ValueError("API key format unsupported; no values printed")
    os.environ.update(
        DEEPSEEK_API_KEY=key,
        OPENAI_BASE_URL="https://api.deepseek.com",
        OPENAI_MODEL=model,
        DEEPSEEK_MODEL=model,
        LLM_MOCK="0",
        TUTOR_COURSE="experimental-psychology-3",
        DATABASE_URL="sqlite:///" + str(output / "legacy.db"),
        COURSE_DATABASE_URL="sqlite:///" + str(output / "course.db"),
        MEMORY_WORKER_ENABLED="0",
        CLEANUP_EXPIRED_ON_STARTUP="0",
        LOCAL_AGENT_LOOP_ENABLED="1",
        ADAPTIVE_TUTORING_ENABLED="1",
        SELECTED_TEXT_AGENT_LOOP_ENABLED="1",
        INPUT_UNDERSTANDING_MODE="active",
        INPUT_UNDERSTANDING_SEMANTIC_ENABLED="0",
        LABELS_POLICY="1",
        LABELS_STRUCTURE="1",
        LABELS_TURN="1",
        Q5_LEARNING_ENABLED="0",
        FIXED_BOOK_RETRIEVAL_ENABLED="0",
        Q3_RETRIEVAL_MODE="stub",
        DEEPTUTOR_NATIVE_ENABLED="0",
        VISUALIZATION_ON_DEMAND="off",
        NO_PROXY="*",
    )
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        os.environ.pop(name, None)


def post(client, student, session, message, request_id=None):
    payload = {
        "student_id": student,
        "session_id": session,
        "request_id": request_id or str(uuid.uuid4()),
        "account_type": "test",
        "message": message,
    }
    started = time.monotonic()
    response = client.post("/api/chat", json=payload)
    body = response.json()
    return {"request": payload, "http_status": response.status_code,
            "seconds": time.monotonic() - started, "result": body}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="deepseek-flash")
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    configure(args.key_file, args.output, args.model)

    from fastapi.testclient import TestClient
    from main import app

    run = uuid.uuid4().hex[:10]
    student = "ch1-live-" + run
    session = "ch1-live-" + run
    report = {"model": args.model, "student": student, "session": session, "cases": []}
    with TestClient(app) as client:
        first = post(client, student, session, "我想学习第一章的主要内容")
        report["cases"].append({"name": "chapter_overview", **first})
        result = first["result"]
        reply = result.get("reply") or ""
        overview = result.get("chapter_overview") or {}
        nav = result.get("course_navigation") or {}
        checks = {
            "http_200": first["http_status"] == 200,
            "answered": result.get("answer_status") == "answered",
            "length_600": len(reply) >= 600,
            "chapter_title": "实验心理学概论" in reply,
            "sections": all(f"第{chinese}节" in reply for chinese in "一二三四"),
            "no_other_book_title": "心理学的实验设计和数据处理" not in reply,
            "coverage_ok": overview.get("coverage_ok") is True,
            "content_ok": overview.get("content_ok") is True,
            "nav_overview": nav.get("status") == "ready" and nav.get("mode") == "overview",
            "no_mastery": not (result.get("teaching") or {}).get("formal_mastery", False),
            "no_step": result.get("step_advanced") is False,
        }
        report["checks"] = checks
        report["reply_len"] = len(reply)

        # Two-turn Fechner follow-up: second turn must not become a file catalog.
        fechner_1 = post(client, student, session, "费希纳是谁")
        report["cases"].append({"name": "fechner_first", **fechner_1})
        fechner_2 = post(client, student, session, "教材中与他相关的内容有哪些，我想学习")
        report["cases"].append({"name": "fechner_followup", **fechner_2})
        result2 = fechner_2["result"]
        reply2 = result2.get("reply") or ""
        report["checks"]["fechner_not_catalog"] = (
            (result2.get("publication_kind") != "catalog")
            and ("共" not in reply2 or "份" not in reply2)
            and ("PDF" not in reply2 or "第1章" not in reply2)
        )
        report["fechner_status"] = result2.get("answer_status")

        # Explicit no-question constraint must suppress the closing question.
        noq = post(client, student, session, "不要出题，只讲第一章主要内容")
        report["cases"].append({"name": "no_questions", **noq})
        noq_reply = noq["result"].get("reply") or ""
        report["checks"]["no_questions_no_mark"] = (
            noq["result"].get("answer_status") in ("answered", "partial")
            and "？" not in noq_reply and "?" not in noq_reply)

        # Explicit file count must still be possible.
        catalog = post(client, student, session, "教材有几本")
        report["cases"].append({"name": "catalog", **catalog})
        report["checks"]["catalog_still_works"] = (
            catalog["result"].get("answer_status") == "answered"
            and ("份" in (catalog["result"].get("reply") or "")
                 or "PDF" in (catalog["result"].get("reply") or "")))

    (args.output / "acceptance.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"checks": report["checks"], "reply_len": report["reply_len"],
                      "seconds": [round(c["seconds"], 2) for c in report["cases"]]},
                     ensure_ascii=False))
    return 0 if all(report["checks"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
