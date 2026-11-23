import unittest

from knowledge.textbook_qa_contract import (
    ALLOWED_INTENTS,
    REFUSAL_MESSAGE,
    answer_shape,
    classify_question,
)


class TextbookQAContractTests(unittest.TestCase):
    def test_concept_definition_and_comparison_are_allowed(self):
        for question in (
            "什么是双盲设计？",
            "信度和效度有什么区别？",
            "全称命题的否定与存在命题是什么关系？",
            "这个公式里的符号表示什么？",
        ):
            with self.subTest(question=question):
                result = classify_question(question)
                self.assertTrue(result.allowed)
                self.assertIn(result.intent, ALLOWED_INTENTS)

    def test_existing_textbook_theorem_explanation_is_allowed(self):
        result = classify_question("教材里定理 7.4 为什么成立？")
        self.assertTrue(result.allowed)
        self.assertEqual(result.intent, "theorem_explanation")

    def test_new_exercises_calculations_and_proofs_are_refused(self):
        for question in (
            "请计算 37×48",
            "求证任意一棵树都至少有两个叶结点",
            "给我出一道新题",
            "设计一个新算法解决这个问题",
        ):
            with self.subTest(question=question):
                result = classify_question(question)
                self.assertFalse(result.allowed)
                self.assertEqual(result.reply, REFUSAL_MESSAGE)

    def test_ambiguous_followup_needs_a_bound_object(self):
        result = classify_question("为什么会这样？")
        self.assertTrue(result.needs_clarification)
        self.assertFalse(result.allowed)
        bound = classify_question("为什么会这样？", has_context=True)
        self.assertFalse(bound.needs_clarification)

    def test_answer_shape_is_fixed(self):
        self.assertEqual(answer_shape(), (
            "直接回答",
            "教材依据和关键条件",
            "简短解释",
            "教材引用",
        ))


if __name__ == "__main__":
    unittest.main()
