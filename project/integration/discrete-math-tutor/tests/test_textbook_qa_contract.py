import unittest
from unittest.mock import Mock

from agents.response_generator import ResponseGenerator
from agents.teaching_planner import TeachingPlan
from knowledge.textbook_qa_contract import (
    ALLOWED_INTENTS,
    TEXTBOOK_ANSWER_FORMAT,
    REFUSAL_MESSAGE,
    answer_shape,
    classify_question,
)
from models.student_state import StudentState


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
            "证明这个结论",
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

    def test_direct_textbook_explanation_receives_four_part_instruction(self):
        llm = Mock()
        llm.chat.return_value = "教材中的定义。[1]"
        result = ResponseGenerator(llm).generate(
            StudentState(),
            TeachingPlan(
                goal="解释集合",
                strategy="worked_example",
                action="explain",
                difficulty="easy",
            ),
            "集合是什么？",
            [],
            instructional_move="direct_explanation",
            textbook_excerpts="[1] 集合 | 1.1.1 | 证据ID:fixture\n集合由对象组成。",
        )
        self.assertEqual(result, "教材中的定义。[1]")
        system = llm.chat.call_args.args[0][0]["content"]
        self.assertIn(TEXTBOOK_ANSWER_FORMAT, system)
        for section in answer_shape():
            self.assertIn(section, system)


if __name__ == "__main__":
    unittest.main()
