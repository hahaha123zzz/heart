import hashlib
import json
import unittest
from pathlib import Path

from knowledge.textbook_qa_errors import classify_error
from scripts.evaluate_textbook_qa import evaluate_case, summarize


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests/data/textbook_qa_holdout_v1.jsonl"


class TextbookQAEvaluationTests(unittest.TestCase):
    def test_dataset_is_frozen_balanced_and_disjointly_split(self):
        rows = [json.loads(line) for line in DATA.read_text(encoding="utf-8").splitlines() if line.strip()]
        frozen = (DATA.with_suffix(".sha256")).read_text(encoding="utf-8").split()[0]
        self.assertEqual(hashlib.sha256(DATA.read_bytes()).hexdigest(), frozen)
        self.assertEqual(len(rows), 60)
        self.assertEqual(sum(row["split"] == "calibration" for row in rows), 30)
        self.assertEqual(sum(row["split"] == "evaluation" for row in rows), 30)
        self.assertEqual(sum(row["route"] == "answer" for row in rows), 36)
        self.assertEqual(sum(row["route"] == "refuse" for row in rows), 18)
        self.assertEqual(sum(row["route"] == "clarify" for row in rows), 6)

    def test_supported_answer_is_correct(self):
        case = {
            "id": "x",
            "route": "answer",
            "category": "definition",
            "section": "目标小节",
            "concept": ["目标概念"],
            "required_groups": [["对象"], ["条件"]],
        }
        response = {
            "answer_status": "answered",
            "reply": "目标概念说明对象需要满足条件。",
            "textbook_sources": ["目标小节"],
            "pdf_references": [{
                "selection_ref": {
                    "location_kind": "exact",
                    "section_title": "目标小节",
                    "quote": "目标概念说明对象需要满足条件。",
                }
            }],
        }
        row = evaluate_case(case, response)
        self.assertEqual(row["error"], "correct")

    def test_missing_condition_is_not_counted_as_correct(self):
        checks = {
            "expected_route": "answer",
            "route_correct": True,
            "invalid_citation": False,
            "retrieval_hit": True,
            "wrong_citation": False,
            "concept_hit": True,
            "required_groups_hit": False,
            "support_groups_hit": False,
            "external_content": False,
        }
        self.assertEqual(classify_error(checks).label, "incomplete_condition")

    def test_summary_separates_refusal_and_clarification(self):
        rows = [
            {
                "route": "refuse",
                "category": "out_of_scope",
                "error": "correct",
                "checks": {"route_correct": True},
                "unsupported_claim": False,
            },
            {
                "route": "clarify",
                "category": "ambiguous",
                "error": "correct",
                "checks": {"route_correct": True},
                "unsupported_claim": False,
            },
        ]
        summary = summarize(rows)
        self.assertEqual(summary["refusal_accuracy"], 1.0)
        self.assertEqual(summary["clarification_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
