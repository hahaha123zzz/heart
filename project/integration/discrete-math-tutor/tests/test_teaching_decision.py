"""决策契约与策略防重复：只记录，不改非困难轮次。"""
import unittest
from unittest.mock import patch

from tests.test_label_consumers import labeled_turn
from tests.test_adaptive_tutoring import prior


class TeachingDecisionTests(unittest.TestCase):
    def test_label_decision_records_source_and_versions(self):
        old = prior()
        with patch.dict('os.environ', {'LABELS_POLICY': '1'}):
            turn = labeled_turn('我还是分不清信度和效度', old=old)
        decision = turn.state['decision']
        self.assertEqual(decision['strategy'], 'contrast')
        self.assertEqual(decision['source'], 'label')
        self.assertEqual(decision['label_strategy'], 'contrast')
        self.assertEqual(decision['ontology_version'], 'psy-6d-v1')
        self.assertEqual(decision['policy_version'], 'teaching-v1')
        self.assertFalse(decision['avoided_repeat'])

    def test_rotation_decision_has_no_label_source(self):
        turn = labeled_turn('我不会', old=prior())
        decision = turn.state['decision']
        self.assertEqual(decision['source'], 'rotation')
        self.assertIsNone(decision['label_strategy'])

    def test_repeated_label_strategy_rotates(self):
        old = prior() | {'last_strategy': 'contrast',
                         'used_strategies': ['contrast', 'contrast', 'contrast']}
        with patch.dict('os.environ', {'LABELS_POLICY': '1'}):
            turn = labeled_turn('我还是分不清信度和效度', old=old)
        self.assertNotEqual(turn.strategy, 'contrast')
        self.assertTrue(turn.state['decision']['avoided_repeat'])

    def test_non_difficulty_turn_is_not_rotated_for_repetition(self):
        old = prior() | {'last_strategy': 'guided_practice',
                         'used_strategies': ['guided_practice', 'guided_practice']}
        turn = labeled_turn('考考我', old=old)
        self.assertEqual(turn.strategy, 'guided_practice')
        self.assertFalse(turn.state['decision']['avoided_repeat'])


if __name__ == '__main__':
    unittest.main()
