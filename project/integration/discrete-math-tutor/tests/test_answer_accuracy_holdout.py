import json
import hashlib
import unittest
from pathlib import Path


DATA = Path(__file__).parent / "data"


class AnswerAccuracyHoldoutTests(unittest.TestCase):
    def test_holdout_is_frozen_stratified_and_disjoint_from_development(self):
        holdout = json.loads((DATA / "e2e_answer_accuracy_holdout_v1.json").read_text(encoding="utf-8"))
        development = json.loads((DATA / "e2e_answer_accuracy_v1.json").read_text(encoding="utf-8"))
        cases = holdout["cases"]
        frozen_hash = (DATA / "e2e_answer_accuracy_holdout_v1.sha256").read_text(
            encoding="utf-8"
        ).split()[0]
        actual_hash = hashlib.sha256(
            (DATA / "e2e_answer_accuracy_holdout_v1.json").read_bytes()
        ).hexdigest()
        self.assertEqual(actual_hash, frozen_hash)
        turns = sum(len(case.get("turns", [])) or 1 for case in cases)
        self.assertEqual(len(cases), 55)
        self.assertEqual(turns, 60)
        self.assertIn("not been used for tuning", holdout["note"])
        counts = {}
        for case in cases:
            counts[case["category"]] = counts.get(case["category"], 0) + 1
        self.assertEqual(counts, {
            "definition": 9,
            "proof": 6,
            "formula": 8,
            "application": 8,
            "paraphrase": 8,
            "multiturn": 5,
            "out_of_scope": 11,
        })
        ids = [case["id"] for case in cases]
        self.assertEqual(len(ids), len(set(ids)))
        holdout_questions = {
            turn["question"].strip()
            for case in cases
            for turn in (case.get("turns") or [case])
        }
        development_questions = {case["question"].strip() for case in development["cases"]}
        self.assertFalse(holdout_questions & development_questions)
        self.assertTrue(all(
            len(case.get("turns") or []) == 2
            for case in cases if case["category"] == "multiturn"
        ))


if __name__ == "__main__":
    unittest.main()
