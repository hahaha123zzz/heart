"""Run a reproducible end-to-end accuracy evaluation against the live chat API."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "tests/data/e2e_answer_accuracy_v1.json"
DEFAULT_OUTPUT = ROOT / ".runtime/answer-accuracy/latest.json"
DEFAULT_INDEX = ROOT / "knowledge/rag_index_v2.sqlite3"
DEFAULT_PDF_MANIFEST = ROOT / "knowledge/pdf/manifest.json"


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _compact(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def _request(base_url: str, method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:1000]
        raise RuntimeError(f"{method} {path} returned HTTP {exc.code}: {detail}") from exc


def _source_text(response: dict) -> str:
    return "\n".join(str(value) for value in response.get("textbook_sources") or [])


def _citation_quotes(response: dict) -> list[str]:
    quotes = []
    for reference in response.get("pdf_references") or []:
        selection = reference.get("selection_ref") or {}
        quote = selection.get("quote") or selection.get("text")
        if quote:
            quotes.append(str(quote))
    return quotes


def _answer_matches(question_case: dict, response: dict) -> bool:
    reply = _compact(response.get("reply"))
    for group in question_case.get("answer_groups") or []:
        if not any(_compact(option) in reply for option in group):
            return False
    return True


def _retrieval_hit(question_case: dict, response: dict) -> bool:
    expected_section = _compact(question_case.get("section"))
    if not expected_section:
        return False
    sources = _compact(_source_text(response))
    if expected_section in sources:
        return True
    for reference in response.get("pdf_references") or []:
        selection = reference.get("selection_ref") or {}
        if expected_section in _compact(selection.get("section_title")):
            return True
    return False


def _citation_integrity(response: dict) -> dict:
    references = response.get("pdf_references") or []
    invalid = []
    for index, reference in enumerate(references, 1):
        selection = reference.get("selection_ref") or {}
        location = selection.get("location_kind")
        quote = selection.get("quote") or selection.get("text")
        if location in {"stale", "unavailable"} or not quote:
            invalid.append(index)
    return {"count": len(references), "invalid": invalid, "valid": len(references) - len(invalid)}


def _citation_supports(question_case: dict, response: dict) -> bool:
    if not _answer_matches(question_case, response):
        return False
    evidence = _compact("\n".join(_citation_quotes(response)))
    if not evidence:
        return False
    for group in question_case.get("answer_groups") or []:
        if not any(_compact(option) in evidence for option in group):
            return False
    return _retrieval_hit(question_case, response)


def score_response(question_case: dict, response: dict) -> dict:
    expect_refusal = bool(question_case.get("expect_refusal"))
    status = str(response.get("answer_status") or "")
    citations = _citation_integrity(response)
    if expect_refusal:
        correct = status != "answered" and citations["count"] == 0
        return {
            "retrieval_hit": None,
            "answer_correct": correct,
            "citation_supports_answer": None,
            "citation_integrity": citations,
            "false_refusal": False,
            "unsupported_answer": status == "answered",
        }
    answer_correct = status == "answered" and _answer_matches(question_case, response)
    retrieval_hit = _retrieval_hit(question_case, response)
    return {
        "retrieval_hit": retrieval_hit,
        "answer_correct": bool(answer_correct and retrieval_hit),
        "citation_supports_answer": bool(answer_correct and _citation_supports(question_case, response)),
        "citation_integrity": citations,
        "false_refusal": status != "answered",
        "unsupported_answer": status == "answered" and not (answer_correct and retrieval_hit),
    }


def _rate(rows: list[dict], key: str) -> float | None:
    values = [row[key] for row in rows if row.get(key) is not None]
    return round(sum(bool(value) for value in values) / len(values), 4) if values else None


def summarize(rows: list[dict]) -> dict:
    in_scope = [row for row in rows if not row["expect_refusal"]]
    refused = [row for row in rows if row["expect_refusal"]]
    categories = defaultdict(list)
    for row in in_scope:
        categories[row["category"]].append(row)
    return {
        "total_scenarios": len({
            row.get("scenario_id") or row.get("id") or f"row-{index}"
            for index, row in enumerate(rows)
        }),
        "total_cases": len(rows),
        "in_scope_cases": len(in_scope),
        "out_of_scope_cases": len(refused),
        "retrieval_hit_rate": _rate(in_scope, "retrieval_hit"),
        "answer_accuracy": _rate(in_scope, "answer_correct"),
        "citation_support_rate": _rate(in_scope, "citation_supports_answer"),
        "false_refusal_rate": _rate(in_scope, "false_refusal"),
        "unsupported_answer_rate": _rate(in_scope, "unsupported_answer"),
        "out_of_scope_refusal_accuracy": _rate(refused, "answer_correct"),
        "invalid_citation_count": sum(len(row["citation_integrity"]["invalid"]) for row in rows),
        "overall_answer_accuracy": _rate(rows, "answer_correct"),
        "categories": {
            name: {
                "cases": len(items),
                "answer_accuracy": _rate(items, "answer_correct"),
                "retrieval_hit_rate": _rate(items, "retrieval_hit"),
            }
            for name, items in sorted(categories.items())
        },
    }


def expand_turns(question_case: dict) -> list[dict]:
    turns = question_case.get("turns")
    if not turns:
        return [{**question_case, "scenario_id": question_case["id"], "turn_index": 1}]
    inherited = {
        key: value for key, value in question_case.items()
        if key not in {"turns", "id", "question", "answer_groups", "expect_refusal"}
    }
    return [
        {
            **inherited,
            **turn,
            "id": f"{question_case['id']}-t{index}",
            "scenario_id": question_case["id"],
            "turn_index": index,
        }
        for index, turn in enumerate(turns, 1)
    ]


def evaluate(
    cases_path: Path,
    base_url: str,
    student_prefix: str,
    *,
    dry_run: bool = False,
) -> dict:
    raw_cases = cases_path.read_bytes()
    dataset = json.loads(raw_cases)
    cases = dataset["cases"]
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    student_id = f"{student_prefix}-{stamp}"[:64]
    turns = [(case, turn) for case in cases for turn in expand_turns(case)]
    metadata = {
        "schema": "answer-accuracy-report-v1",
        "created_at": datetime.now().astimezone().isoformat(),
        "dataset": dataset.get("dataset"),
        "dataset_note": dataset.get("note"),
        "cases_file": str(cases_path),
        "cases_sha256": hashlib.sha256(raw_cases).hexdigest(),
        "index_sha256": _sha256(DEFAULT_INDEX),
        "pdf_manifest_sha256": _sha256(DEFAULT_PDF_MANIFEST),
        "scenario_count": len(cases),
        "turn_count": len(turns),
        "dry_run": dry_run,
    }
    if dry_run:
        return metadata
    health = _request(base_url, "GET", "/health")
    _request(base_url, "POST", "/api/accounts/test", {"student_id": student_id, "ttl_hours": 2})
    rows = []
    started = time.perf_counter()
    try:
        for case, turn in turns:
            turn_started = time.perf_counter()
            response = _request(base_url, "POST", "/api/chat", {
                "student_id": student_id,
                "message": turn["question"],
                "account_type": "test",
                "session_id": f"accuracy-{stamp}-{turn['scenario_id']}",
            })
            score = score_response(turn, response)
            rows.append({
                "id": turn["id"],
                "scenario_id": turn["scenario_id"],
                "turn_index": turn["turn_index"],
                "question": turn["question"],
                "category": turn["category"],
                "expect_refusal": bool(turn.get("expect_refusal")),
                **score,
                "status": response.get("answer_status"),
                "knowledge_point": response.get("knowledge_point"),
                "reply": response.get("reply"),
                "textbook_sources": response.get("textbook_sources") or [],
                "pdf_references": response.get("pdf_references") or [],
                "elapsed_ms": round((time.perf_counter() - turn_started) * 1000, 1),
            })
    finally:
        try:
            _request(base_url, "DELETE", f"/api/accounts/test/{student_id}")
        except RuntimeError:
            pass
    return metadata | {
        "service_health": health,
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "summary": summarize(rows),
        "rows": rows,
    }


def _format_rate(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.1%}"


def write_markdown(report: dict, path: Path) -> None:
    if report.get("dry_run"):
        path.write_text(
            "# Answer Accuracy Dataset Freeze\n\n"
            f"- Dataset: `{report['dataset']}`\n"
            f"- Cases SHA-256: `{report['cases_sha256']}`\n"
            f"- Index SHA-256: `{report['index_sha256']}`\n"
            f"- Scenarios: {report['scenario_count']}\n"
            f"- Turns: {report['turn_count']}\n",
            encoding="utf-8",
        )
        return
    summary = report["summary"]
    lines = [
        "# Answer Accuracy Report",
        "",
        f"- Dataset: `{report['dataset']}`",
        f"- Cases SHA-256: `{report['cases_sha256']}`",
        f"- Index SHA-256: `{report['index_sha256']}`",
        f"- Model mode: `mock={report['service_health'].get('mock_mode')}`",
        f"- Total cases: {summary['total_cases']}",
        "",
        "| Metric | Result |",
        "| --- | ---: |",
        f"| Retrieval Hit | {_format_rate(summary['retrieval_hit_rate'])} |",
        f"| Answer Accuracy (in-scope) | {_format_rate(summary['answer_accuracy'])} |",
        f"| Citation Support (heuristic) | {_format_rate(summary['citation_support_rate'])} |",
        f"| False Refusal | {_format_rate(summary['false_refusal_rate'])} |",
        f"| Unsupported Answer | {_format_rate(summary['unsupported_answer_rate'])} |",
        f"| Out-of-scope Refusal | {_format_rate(summary['out_of_scope_refusal_accuracy'])} |",
        f"| Invalid Citations | {summary['invalid_citation_count']} |",
        f"| Overall Answer Accuracy | {_format_rate(summary['overall_answer_accuracy'])} |",
        "",
        "Citation support is a deterministic evidence-alignment check, not a semantic-entailment model.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--student-prefix", default="answer-accuracy")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    report = evaluate(args.cases, args.base_url, args.student_prefix, dry_run=args.dry_run)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown = args.output.with_suffix(".md")
    write_markdown(report, markdown)
    print(json.dumps(report.get("summary", {
        "scenarios": report["scenario_count"],
        "turns": report["turn_count"],
        "cases_sha256": report["cases_sha256"],
    }), ensure_ascii=False, indent=2))
    print(f"JSON: {args.output}")
    print(f"Markdown: {markdown}")
