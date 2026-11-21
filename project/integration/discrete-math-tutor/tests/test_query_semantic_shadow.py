import hashlib
import json
import unittest
from pathlib import Path

from scripts.evaluate_query_semantic_shadow import enable_gates, evaluate_rows


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests/data"


class QuerySemanticShadowTests(unittest.TestCase):
    def test_annotation_set_is_frozen_and_has_one_reviewer(self):
        path = DATA / "semantic_query_annotations_v1.jsonl"
        frozen = (DATA / "semantic_query_annotations_v1.sha256").read_text(
            encoding="utf-8"
        ).split()[0]
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), frozen)
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(len(rows), 60)
        self.assertEqual(
            sum(row["split"] == "calibration" for row in rows),
            30,
        )
        self.assertEqual(
            sum(row["split"] == "evaluation" for row in rows),
            30,
        )
        self.assertEqual({row["review_count"] for row in rows}, {1})

    def test_metrics_separate_concept_quality_from_abstention(self):
        rows = [
            {
                "id": "one",
                "text": "问题一",
                "answerable": True,
                "section": "目标小节",
                "semantic": [
                    {"title": "目标小节", "score": 0.8},
                    {"title": "其他小节", "score": 0.7},
                ],
                "baseline": [{"title": "其他小节"}],
            },
            {
                "id": "two",
                "text": "问题二",
                "answerable": False,
                "section": None,
                "semantic": [
                    {"title": "教材相邻小节", "score": 0.4},
                ],
                "baseline": [{"title": "教材相邻小节"}],
            },
        ]
        metrics = evaluate_rows(rows, threshold=0.5)
        self.assertEqual(metrics["concept_f1"], 1.0)
        self.assertEqual(metrics["out_of_scope_f1"], 1.0)
        self.assertEqual(metrics["section_recall_at_3"], 1.0)

    def test_one_reviewer_cannot_enable_the_semantic_path(self):
        metrics = {
            "section_recall_at_3": 0.95,
            "baseline_section_recall_at_3": 0.6,
            "concept_f1": 0.82,
            "out_of_scope_f1": 0.89,
        }
        gates = enable_gates(metrics, [1] * 30)
        self.assertTrue(gates["semantic_recall_at_3_improves_baseline"])
        self.assertTrue(gates["concept_f1_at_least_0_75"])
        self.assertTrue(gates["out_of_scope_f1_at_least_0_80"])
        self.assertFalse(gates["two_independent_reviews"])
        self.assertFalse(all(gates.values()))

    def test_semantic_model_is_not_imported_by_active_answer_path(self):
        source = (ROOT / "orchestrator.py").read_text(encoding="utf-8")
        self.assertNotIn("query_semantic_shadow", source)


if __name__ == "__main__":
    unittest.main()
