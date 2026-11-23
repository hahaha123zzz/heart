"""Compare paragraph retrieval with complete textbook-unit retrieval."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from knowledge.knowledge_units import retrieve_units
from knowledge.query_understanding import understand
from knowledge.textbook import load_textbook
from orchestrator import retrieve_course


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "tests/data/textbook_qa_holdout_v1.jsonl"
DEFAULT_OUTPUT = ROOT / ".runtime/textbook-qa/unit-comparison.json"


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def _groups(groups: list[list[str]], text: str) -> bool:
    compact = _compact(text)
    return all(any(_compact(option) in compact for option in group) for group in groups)


def _metrics(rows: list[dict], key: str) -> dict:
    count = len(rows)
    return {
        "section_hit": round(sum(row[f"{key}_section_hit"] for row in rows) / count, 4),
        "concept_coverage": round(
            sum(row[f"{key}_concept_hit"] for row in rows) / count, 4
        ),
        "condition_coverage": round(
            sum(row[f"{key}_conditions_hit"] for row in rows) / count, 4
        ),
        "average_context_chars": round(
            sum(row[f"{key}_chars"] for row in rows) / count, 1
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--split", choices=("calibration", "evaluation", "all"), default="calibration")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    cases = [
        json.loads(line)
        for line in args.cases.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    cases = [
        case for case in cases
        if case["route"] == "answer"
        and (args.split == "all" or case["split"] == args.split)
    ]
    chunks = load_textbook()
    rows = []
    for case in cases:
        understanding = understand(case["question"])
        current = retrieve_course(case["question"], chunks, limit=3)
        units = retrieve_units(
            case["question"],
            limit=3,
            section_hints=tuple(candidate.section_id for candidate in understanding.candidates),
        )
        current_text = "\n".join(source.text for source in current)
        unit_text = "\n".join(source.text for source in units)
        rows.append({
            "id": case["id"],
            "question": case["question"],
            "section": case["section"],
            "current_section_hit": _compact(case["section"]) in _compact(
                "\n".join(source.section for source in current)
            ),
            "unit_section_hit": _compact(case["section"]) in _compact(
                "\n".join(source.section for source in units)
            ),
            "current_concept_hit": any(
                _compact(term) in _compact(current_text) for term in case.get("concept") or ()
            ),
            "unit_concept_hit": any(
                _compact(term) in _compact(unit_text) for term in case.get("concept") or ()
            ),
            "current_conditions_hit": _groups(case.get("required_groups") or [], current_text),
            "unit_conditions_hit": _groups(case.get("required_groups") or [], unit_text),
            "current_chars": len(current_text),
            "unit_chars": len(unit_text),
            "current_units": [
                {"kind": source.kind, "section": source.section, "id": source.chunk_id}
                for source in current
            ],
            "unit_units": [
                {"kind": source.kind, "section": source.section, "id": source.chunk_id}
                for source in units
            ],
        })
    report = {
        "schema": "textbook-unit-comparison-v1",
        "created_at": datetime.now().astimezone().isoformat(),
        "split": args.split,
        "cases": len(rows),
        "current": _metrics(rows, "current"),
        "unit_retrieval": _metrics(rows, "unit"),
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "cases": len(rows),
        "current": report["current"],
        "unit_retrieval": report["unit_retrieval"],
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
