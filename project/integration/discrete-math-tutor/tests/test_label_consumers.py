"""P3 三个消费者：策略定向、回答结构、回合边界。默认关闭。"""
import unittest
from copy import deepcopy
from unittest.mock import Mock, patch

from agents.adaptive_tutoring import TeachingTurn
from agents.input_understanding.service import understand
from models.chat_request import ChatRequest
from models.task_context import TaskContext
from tests.test_adaptive_tutoring import prior


def labeled_turn(message, *, old=None):
    context = TaskContext(student_id='s', session_id='x', knowledge_point='自变量',
                          message=message, tutoring=deepcopy(old or {}), input_mode='active')
    request = ChatRequest(student_id='s', session_id='x', request_id='r', message=message)
    context.input_understanding = understand(context, request)
    return TeachingTurn(context, request, Mock(),
                        validate_sources=lambda rows: deepcopy(rows))


class LabelConsumerTests(unittest.TestCase):
    def test_policy_switch_targets_discrimination_instead_of_rotating(self):
        old = prior(last_strategy='contrast')
        old.pop('strategy_plan',None)
        with patch.dict('os.environ', {}):
            off = labeled_turn('我还是分不清信度和效度', old=old)
        self.assertEqual(off.strategy, 'worked_example')
        self.assertIsNone(off.label_strategy)
        with patch.dict('os.environ', {'LABELS_POLICY': '1'}):
            on = labeled_turn('我还是分不清信度和效度', old=old)
        self.assertEqual(on.strategy, 'worked_example')
        self.assertEqual(on.label_strategy, 'worked_example')

    def test_policy_switch_supports_comprehension_without_rotation(self):
        old = prior(last_strategy='contrast')
        with patch.dict('os.environ', {'LABELS_POLICY': '1'}):
            turn = labeled_turn('我没听懂', old=old)
        self.assertEqual(turn.plan.primary_strategy, 'worked_example')

    def test_structure_note_reaches_instructions_only_when_enabled(self):
        message = '帮我设计一个心理学实验'
        with patch.dict('os.environ', {}):
            self.assertNotIn('先列约束', labeled_turn(message).instructions())
        with patch.dict('os.environ', {'LABELS_STRUCTURE': '1'}):
            self.assertIn('先列约束', labeled_turn(message).instructions())

    def test_skip_signal_closes_turn_and_releases_pending(self):
        old = prior(pending=True)
        with patch.dict('os.environ', {}):
            off = labeled_turn('这题我不想做了', old=old)
        self.assertFalse(off.skip)
        self.assertIsNotNone(off.progress.pending_question)
        with patch.dict('os.environ', {'LABELS_TURN': '1'}):
            on = labeled_turn('这题我不想做了', old=old)
        self.assertTrue(on.skip)
        self.assertIsNone(on.progress.pending_question)
        self.assertEqual(on.state['turn_move'], 'check_skipped')

    def test_answer_seeking_without_disclosure_states_the_limit(self):
        message = '直接告诉我答案，不要给我完整答案'
        with patch.dict('os.environ', {'LABELS_TURN': '1'}):
            turn = labeled_turn(message)
            text = turn.instructions()
        self.assertTrue(turn.limit_disclosure)
        self.assertIn('禁止完整答案', text)
        self.assertNotIn('完整说明步骤和答案', text)
        with patch.dict('os.environ', {}):
            self.assertFalse(labeled_turn(message).limit_disclosure)

    def test_limit_wins_over_full_explanation_when_a_question_is_pending(self):
        old = prior(pending=True)
        message = '直接告诉我答案，不要给我完整答案'
        with patch.dict('os.environ', {'LABELS_TURN': '1'}):
            text = labeled_turn(message, old=old).instructions()
        self.assertIn('禁止完整答案', text)
        self.assertNotIn('完整说明步骤和答案', text)


if __name__ == '__main__':
    unittest.main()
