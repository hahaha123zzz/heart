"""Evaluate textbook-only routing, retrieval, completeness and citation support."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from knowledge.textbook_qa_errors import classify_error


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "tests/data/textbook_qa_holdout_v1.jsonl"
DEFAULT_OUTPUT = ROOT / ".runtime/textbook-qa/latest.json"


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def _request(base_url: str, method: str, path: str, body: dict | None = None) -> dict:
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8") if body else None,
        method=method,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.load(response)


def _sources(response: dict) -> str:
    values = list(response.get("textbook_sources") or ())
    for reference in response.get("pdf_references") or ():
        selection = reference.get("selection_ref") or {}
        values.append(selection.get("section_title") or "")
    return "\n".join(str(value) for value in values)


def _quotes(response: dict) -> str:
    values = []
    for reference in response.get("pdf_references") or ():
        selection = reference.get("selection_ref") or {}
        values.append(selection.get("quote") or selection.get("text") or "")
    return "\n".join(values)


def _groups_present(groups: list[list[str]], text: str) -> bool:
    compact = _compact(text)
    return all(any(_compact(option) in compact for option in group) for group in groups)


def evaluate_case(case: dict, response: dict) -> dict:
    status = str(response.get("answer_status") or "")
    reply = str(response.get("reply") or "")
    expected_route = case["route"]
    if expected_route == "answer":
        route_correct = status == "answered"
    elif expected_route == "refuse":
        route_correct = (
            status != "answered"
            and not response.get("pdf_references")
            and any(term in reply for term in ("只回答教材", "没有教材", "无法", "不能", "不足"))
        )
    else:
        route_correct = status in {"awaiting_clarification", "routing_stopped"}
    sources = _sources(response)
    quotes = _quotes(response)
    answer_text = reply + "\n" + quotes
    invalid_citation = any(
        (reference.get("selection_ref") or {}).get("location_kind") in {"stale", "unavailable"}
        or not ((reference.get("selection_ref") or {}).get("quote")
                or (reference.get("selection_ref") or {}).get("text"))
        for reference in response.get("pdf_references") or ()
    )
    expected_section = case.get("section")
    retrieval_hit = bool(
        expected_section
        and _compact(expected_section) in _compact(sources + "\n" + quotes)
    )
    reference_sections = [
        _compact((reference.get("selection_ref") or {}).get("section_title"))
        for reference in response.get("pdf_references") or ()
    ]
    wrong_citation = bool(
        expected_route == "answer"
        and any(expected_section and _compact(expected_section) not in section
                for section in reference_sections if section)
    )
    concepts = case.get("concept") or []
    concept_hit = any(_compact(term) in _compact(answer_text) for term in concepts)
    required_groups_hit = _groups_present(case.get("required_groups") or [], reply)
    support_groups_hit = _groups_present(case.get("required_groups") or [], quotes)
    unsupported = expected_route == "answer" and route_correct and not support_groups_hit
    external_content = expected_route == "answer" and route_correct and not quotes
    checks = {
        "expected_route": expected_route,
        "route_correct": route_correct,
        "invalid_citation": invalid_citation,
        "retrieval_hit": retrieval_hit,
        "wrong_citation": wrong_citation,
        "concept_hit": concept_hit,
        "required_groups_hit": required_groups_hit,
        "support_groups_hit": support_groups_hit,
        "external_content": external_content,
    }
    error = classify_error(checks)
    return {
        **case,
        "checks": checks,
        "error": error.label,
        "error_reason": error.reason,
        "unsupported_claim": unsupported,
        "status": status,
        "reply": reply,
        "textbook_sources": response.get("textbook_sources") or [],
        "pdf_references": response.get("pdf_references") or [],
    }


def summarize(rows: list[dict]) -> dict:
    by_category = defaultdict(list)
    for row in rows:
        by_category[row["category"]].append(row)
    answer_rows = [row for row in rows if row["route"] == "answer"]
    refuse_rows = [row for row in rows if row["route"] == "refuse"]
    clarify_rows = [row for row in rows if row["route"] == "clarify"]

    def rate(group, key):
        return round(sum(bool(row["checks"][key]) for row in group) / len(group), 4) if group else 0.0

    return {
        "cases": len(rows),
        "answer_cases": len(answer_rows),
        "refuse_cases": len(refuse_rows),
        "clarify_cases": len(clarify_rows),
        "route_accuracy": rate(rows, "route_correct"),
        "retrieval_hit_rate": rate(answer_rows, "retrieval_hit"),
        "concept_accuracy": rate(answer_rows, "concept_hit"),
        "condition_completeness": rate(answer_rows, "required_groups_hit"),
        "citation_support_rate": rate(answer_rows, "support_groups_hit"),
        "wrong_citation_rate": rate(answer_rows, "wrong_citation"),
        "unsupported_claim_rate": round(
            sum(row["unsupported_claim"] for row in answer_rows) / len(answer_rows), 4
        ) if answer_rows else 0.0,
        "refusal_accuracy": rate(refuse_rows, "route_correct"),
        "clarification_rate": rate(clarify_rows, "route_correct"),
        "error_counts": dict(Counter(row["error"] for row in rows)),
        "categories": {
            name: {
                "cases": len(items),
                "correct": sum(row["error"] == "correct" for row in items),
            }
            for name, items in sorted(by_category.items())
        },
    }


def _load(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def evaluate(path: Path, base_url: str, split: str) -> dict:
    raw = path.read_bytes()
    cases = _load(path)
    selected = [case for case in cases if split == "all" or case["split"] == split]
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    student_id = f"textbook-qa-{stamp}"[:64]
    _request(base_url, "POST", "/api/accounts/test", {
        "student_id": student_id,
        "ttl_hours": 2,
    })
    rows = []
    started = time.perf_counter()
    try:
        for case in selected:
            response = _request(base_url, "POST", "/api/chat", {
                "student_id": student_id,
                "message": case["question"],
                "account_type": "test",
                "session_id": f"textbook-qa-{case['id']}",
            })
            rows.append(evaluate_case(case, response))
    finally:
        try:
            _request(base_url, "DELETE", f"/api/accounts/test/{student_id}")
        except OSError:
            pass
    return {
        "schema": "textbook-qa-evaluation-v1",
        "created_at": datetime.now().astimezone().isoformat(),
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "split": split,
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "summary": summarize(rows),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--split", choices=("calibration", "evaluation", "all"), default="calibration")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = evaluate(args.cases, args.base_url, args.split)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(str(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
