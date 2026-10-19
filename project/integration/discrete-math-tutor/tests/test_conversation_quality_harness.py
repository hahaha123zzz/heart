"""Q1.1：连续对话质量样本的结构与判定自检。"""
import unittest

from scripts.check_conversation_quality import load_cases, self_test


class ConversationQualityHarnessTests(unittest.TestCase):
    def test_cases_load_with_unique_ids_and_turns(self):
        cases = load_cases()
        ids = [case["id"] for case in cases]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(case.get("turns") for case in cases))
        self.assertIn("simplify_without_switching", ids)
        self.assertIn("comparison_followup", ids)
        self.assertIn("accuracy_is_not_hint", ids)
        self.assertIn("explicit_hint_then_explain", ids)

    def test_refusal_case_requires_evidence_rejection_not_citation(self):
        from scripts.check_conversation_quality import _live_checks

        case = {"id": "refusal", "kind": "refusal", "turns": ["请报告真实数值"]}
        result = {"answer_status": "evidence_rejected", "reply": "没有可靠数据",
                  "quality": None, "pdf_references": [], "task_execution": {}}
        checks = _live_checks(case, [result], [[]])
        self.assertTrue(checks["refused"])
        self.assertTrue(checks["no_published_answer"])
        self.assertNotIn("has_citation", checks)

    def test_hint_case_exposes_hint_scope(self):
        from scripts.check_conversation_quality import _live_checks

        case = {"id": "hint", "kind": "hint", "turns": ["只给一个提示"]}
        result = {"answer_status": "answered", "reply": "提示[1]",
                  "quality": {"passed": True, "issues": []},
                  "pdf_references": [{"source_index": 0}],
                  "task_execution": {"hint_only": True, "learning_intents": ["hint"]}}
        checks = _live_checks(case, [result], [[]])
        self.assertTrue(checks["hint_scope"])

    def test_golden_text_cases_are_normalized_to_turns(self):
        from scripts.check_conversation_quality import load_golden_text_cases

        cases = load_golden_text_cases()
        self.assertTrue(cases)
        self.assertTrue(all(case.get("turns") and len(case["turns"]) == 1 for case in cases))
        self.assertTrue(all(case["kind"] in {"answer", "hint", "refusal"} for case in cases))

    def test_dependent_case_is_ordered_after_its_parent(self):
        from scripts.check_conversation_quality import order_cases

        ordered = order_cases([{"id": "followup", "follows": "concept"},
                                {"id": "concept"}])
        self.assertEqual([case["id"] for case in ordered], ["concept", "followup"])

    def test_self_test_passes_and_marks_deferred_cases(self):
        report = self_test()
        self.assertTrue(report["passed"])
        self.assertEqual(report["cases"], 6)
        self.assertIn("clarify_and_continue", report["deferred"])
        self.assertIn("correct_and_forget", report["deferred"])


if __name__ == "__main__":
    unittest.main()
