"""长回答回归：回答不设字数上限，真实生成/核验路径不因长度拒绝或截断。"""
import unittest
from unittest.mock import Mock

from agents.quality_checker import QualityChecker
from agents.response_generator import ResponseGenerator
from agents.task_execution import TaskExecution
from agents.teaching_planner import TeachingPlan
from models.student_state import StudentState


class LongAnswerPublicationTests(unittest.TestCase):
    def test_long_answer_is_published_without_length_rejection(self):
        reply = "这是完整讲解。" * 1000  # 约 7000 字
        llm = Mock()
        llm.chat.return_value = reply
        plan = TeachingPlan(goal="解释", strategy="worked_example", action="explain", difficulty="medium")
        result = ResponseGenerator(llm).generate(
            StudentState(), plan, "请完整讲解第一章", [],
            task_execution=TaskExecution(learning_intents=["explain"]))
        self.assertEqual(result, reply)
        self.assertGreaterEqual(len(result), 6000)
        self.assertEqual(llm.chat.call_args.kwargs["max_tokens"], 8000)
        self.assertEqual(QualityChecker._rule_check(result, plan, {}), [])


if __name__ == "__main__":
    unittest.main()
