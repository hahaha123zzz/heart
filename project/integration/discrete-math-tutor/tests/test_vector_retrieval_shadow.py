import hashlib
import json
import unittest
from pathlib import Path

from scripts.evaluate_vector_retrieval_shadow import enable_gates, _metrics


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests/data"


class VectorRetrievalShadowTests(unittest.TestCase):
    def test_holdout_is_frozen_and_balanced(self):
        path = DATA / "vector_retrieval_holdout_v1.jsonl"
        frozen = (DATA / "vector_retrieval_holdout_v1.sha256").read_text(
            encoding="utf-8"
        ).split()[0]
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), frozen)
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(len(rows), 50)
        self.assertEqual(sum(row["answerable"] for row in rows), 35)
        self.assertEqual(sum(not row["answerable"] for row in rows), 15)

    def test_metrics_use_section_recall_and_negative_rejection(self):
        rows = [
            {
                "answerable": True,
                "section": "目标小节",
                "candidate": [{"title": "目标小节"}],
                "candidate_ms": 10,
            },
            {
                "answerable": False,
                "section": None,
                "candidate": [],
                "candidate_ms": 20,
            },
        ]
        metrics = _metrics(rows, "candidate")
        self.assertEqual(metrics["section_recall_at_3"], 1.0)
        self.assertEqual(metrics["out_of_scope_rejection_f1"], 1.0)

    def test_small_recall_gain_does_not_enable_vector_default(self):
        baseline = {
            "section_recall_at_3": 0.8857,
            "out_of_scope_rejection_f1": 0.80,
            "latency_p95_ms": 204.49,
        }
        vector = {
            "section_recall_at_3": 0.9143,
            "out_of_scope_rejection_f1": 0.9655,
            "latency_p95_ms": 291.18,
        }
        gates = enable_gates(baseline, vector)
        self.assertTrue(gates["out_of_scope_f1_at_least_0_85"])
        self.assertTrue(gates["p95_latency_at_most_2000_ms"])
        self.assertFalse(gates["recall_at_3_beats_current_by_0_05"])
        self.assertFalse(all(gates.values()))

    def test_shadow_index_is_not_referenced_by_active_answer_path(self):
        source = (ROOT / "orchestrator.py").read_text(encoding="utf-8")
        self.assertNotIn("vector-retrieval-shadow", source)


if __name__ == "__main__":
    unittest.main()
