import unittest

from scripts.evaluate_answer_accuracy import score_response, summarize


class AnswerAccuracyEvalTests(unittest.TestCase):
    def case(self):
        return {
            "category": "definition",
            "section": "集合及其元素",
            "answer_groups": [["正整数"], ["组成对象"]],
        }

    def response(self, **overrides):
        value = {
            "answer_status": "answered",
            "reply": "组成对象是正整数。",
            "textbook_sources": ["教材｜1.1.1 集合及其元素"],
            "pdf_references": [{
                "selection_ref": {
                    "section_title": "1.1.1 集合及其元素",
                    "location_kind": "exact",
                    "quote": "其组成对象是正整数。",
                }
            }],
        }
        value.update(overrides)
        return value

    def test_correct_supported_answer(self):
        score = score_response(self.case(), self.response())
        self.assertTrue(score["retrieval_hit"])
        self.assertTrue(score["answer_correct"])
        self.assertTrue(score["citation_supports_answer"])

    def test_wrong_answer_is_not_counted_as_retrieval_accuracy(self):
        score = score_response(self.case(), self.response(reply="组成对象是自然数。"))
        self.assertTrue(score["retrieval_hit"])
        self.assertFalse(score["answer_correct"])
        self.assertFalse(score["citation_supports_answer"])

    def test_invalid_citation_is_reported(self):
        response = self.response()
        response["pdf_references"][0]["selection_ref"]["location_kind"] = "stale"
        score = score_response(self.case(), response)
        self.assertEqual(score["citation_integrity"]["invalid"], [1])

    def test_out_of_scope_refusal(self):
        case = {"category": "out_of_scope", "expect_refusal": True}
        score = score_response(case, {
            "answer_status": "evidence_rejected",
            "textbook_sources": [],
            "pdf_references": [],
        })
        self.assertTrue(score["answer_correct"])
        summary = summarize([{
            "expect_refusal": True,
            "category": "out_of_scope",
            **score,
        }])
        self.assertEqual(summary["out_of_scope_refusal_accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()
