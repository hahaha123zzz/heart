"""路由异常不能触发检索、教学或学习证据写入。"""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from agents.conversation_router import ConversationRouter, RoutingResult
from llm.client import LLMError, LLMJSONError, LLMClient


def valid(**changes):
    value = dict(student_move="question", move_status="", intent="continue",
                 topic="", confidence=0.8, reason="明确的数学问题", needs_context=False)
    value.update(changes)
    return value


class RoutingValidationTests(unittest.TestCase):
    def test_non_finite_values_cannot_authorize_topic_switch(self):
        for score in (float("nan"), float("inf"), -float("inf")):
            with self.subTest(score=score):
                result = ConversationRouter._validate(valid(intent="switch_topic", topic="集合", confidence=score))
                self.assertEqual(result.status, "parse_error")
                self.assertEqual(result.confidence, 0.0)

    def test_malformed_output_is_not_normal_continue(self):
        invalid = [{}, [], None, "bad", valid(intent="delete_all"),
                   valid(student_move="made_up"), valid(confidence="0.9"),
                   valid(confidence=True), valid(confidence=-0.1),
                   valid(confidence=1.1), valid(needs_context="false"),
                   valid(topic=["集合"]), valid(reason="x" * 1001),
                   valid(move_status="adequate"), valid(student_move="attempt", move_status=""),
                   valid(status="unavailable")]
        for value in invalid:
            with self.subTest(value=value):
                self.assertEqual(ConversationRouter._validate(value).status, "parse_error")

    def test_missing_switch_target_is_unknown(self):
        result = ConversationRouter._validate(valid(intent="switch_topic", topic=""))
        self.assertEqual(result.status, "unknown")
        self.assertEqual(result.intent, "clarify_task")

    def test_all_existing_flow_intents_remain_supported(self):
        for intent in ("continue", "switch_topic", "new_goal", "off_task", "clarify_task"):
            result = ConversationRouter._validate(valid(intent=intent, topic="集合" if intent in ("switch_topic", "new_goal") else ""))
            self.assertEqual(result.status, "ok")
            self.assertEqual(result.intent, intent)

    def test_legacy_missing_context_flag_is_inferred(self):
        data = valid(); data.pop("needs_context")
        self.assertFalse(ConversationRouter._validate(data).needs_context)
        data.update(student_move="attempt", move_status="partial")
        self.assertTrue(ConversationRouter._validate(data).needs_context)

    def test_gateway_failure_is_explicit(self):
        llm = Mock(); llm.chat_json.side_effect = LLMError("network failure")
        result = ConversationRouter(llm).route("解释交集", "集合", [], [])
        self.assertEqual(result.status, "unavailable")
        self.assertNotIn("network failure", result.reason)
        self.assertEqual(llm.chat_json.call_count, 1)

    def test_json_parse_error_and_transport_error_are_distinct(self):
        for error, expected in ((ValueError("invalid JSON"), LLMJSONError),
                                (LLMError("transport failed"), LLMError)):
            client = LLMClient(mock=False)
            with patch.object(client, "chat", side_effect=error) as call:
                with self.assertRaises(expected) as caught:
                    client.chat_json([], retries=0)
            self.assertEqual(type(caught.exception), expected)
            self.assertEqual(call.call_count, 1)
        llm = Mock(); llm.chat_json.side_effect = LLMJSONError("bad output")
        self.assertEqual(ConversationRouter(llm).route("解释交集", "集合", [], []).status, "parse_error")

    def test_failure_does_not_commit_to_real_isolated_memory(self):
        from tests.test_memory_events import MemoryEventTests
        fixture = MemoryEventTests()
        fixture.setUp()
        try:
            tutor = fixture.make_tutor("question")
            tutor.conversation_router.route.return_value = RoutingResult.failure("parse_error", "不合规输出")
            token = fixture.memory.repo.memory_token("s", fixture.point)
            result = tutor.handle_turn("s", "解释这个", learning_goal=fixture.point)
            self.assertEqual(result["answer_status"], "routing_failed")
            self.assertEqual(fixture.memory.repo.memory_token("s", fixture.point), token)
            self.assertEqual(fixture.memory.get_history("s"), [])
            self.assertEqual(fixture.memory.list_evidence("s"), [])
            self.assertEqual(fixture.memory.get_state("s", fixture.point).mastery, .5)
        finally:
            fixture.tearDown()

    def test_mock_gateway_still_supports_topic_switch(self):
        result = ConversationRouter(LLMClient(mock=True)).route("我想学集合", "图", [], [])
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.topic, "集合")

    def test_invalid_route_stops_before_retrieval_and_memory_updates(self):
        from orchestrator import TutorOrchestrator
        for status in ("parse_error", "unknown", "unavailable"):
            tutor = TutorOrchestrator.__new__(TutorOrchestrator)
            tutor.memory = Mock()
            tutor.memory.get_history.return_value = []
            tutor.memory.get_active_goal.return_value = "图"
            tutor.memory.list_knowledge_points.return_value = []
            tutor.memory.get_state.return_value = SimpleNamespace(model_dump=lambda: {"mastery": 0.6})
            tutor.conversation_router = Mock()
            tutor.conversation_router.route.return_value = RoutingResult(status=status, intent="clarify_task", confidence=0)
            progress = Mock()
            with patch("orchestrator.retrieve_hybrid") as retrieval:
                result = tutor.handle_turn("validation-student", "这个", progress=progress)
            retrieval.assert_not_called()
            self.assertFalse(result["step_advanced"])
            self.assertEqual(result["routing"]["status"], status)
            self.assertEqual(result["student_state"]["mastery"], 0.6)
            for method in ("append", "commit_learning_turn", "set_active_goal", "save_state", "save_lesson_plan"):
                getattr(tutor.memory, method).assert_not_called()


if __name__ == "__main__":
    unittest.main()
