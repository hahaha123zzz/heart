"""长回答回归：回答不设字数上限，发布路径不因长度拒绝或截断。"""
import unittest

from agents.agent_loop import LocalAgentLoop
from agents.agent_loop_service import _map_result
from agents.q3_navigation import LearningTarget
from agents.tool_protocol import ToolRegistry
from tests.test_q3_agent_loop import ScriptedLLM, final_round, request


class LongAnswerPublicationTests(unittest.TestCase):
    def test_long_answer_is_published_without_length_rejection(self):
        reply = "这是完整讲解。" * 1000
        llm = ScriptedLLM([final_round(reply)])
        result = LocalAgentLoop(llm).run(
            request(llm, ToolRegistry(), publish_gate=lambda text, outcome: (True, "")))
        self.assertTrue(result.completed)
        self.assertEqual(result.final_text, reply)
        self.assertGreaterEqual(len(result.final_text), 6000)
        self.assertNotIn("回复过长", result.final_text)
        mapped = _map_result(result, LearningTarget("kp:x", "概念"))
        self.assertEqual(mapped["answer_status"], "answered")
        self.assertGreaterEqual(len(mapped["reply"]), 6000)


if __name__ == "__main__":
    unittest.main()
