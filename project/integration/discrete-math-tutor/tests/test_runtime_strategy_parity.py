"""三套策略路径的词表对照：都能归一到 13 个库 id。

本测试不要求三条路径选同一个动作（它们职责不同），只锁定“词表不分叉”。
删除旧词表（P5）前必须保持本测试通过。
"""
import unittest
from unittest.mock import Mock

from agents.adaptive_tutoring import analyze_teaching_turn
from agents.strategy_router import StrategyRouter
from agents.teaching_policy import canonical_strategy, select_policy, strategy_ids
from models.student_state import StudentState

MESSAGES = ('什么是自变量', '我不会', '我还是分不清信度和效度', '考考我', '先讲不考')
PREVIOUS = ('', 'contrast', 'worked_example', 'hint')
STATES = (
    StudentState(mastery=0.2),
    StudentState(mastery=0.5),
    StudentState(mastery=0.9),
    StudentState(mastery=0.5, confidence=0.9),
    StudentState(mastery=0.5, emotion='confused'),
    StudentState(mastery=0.5, misconception='把相关当因果'),
)


class RuntimeStrategyParityTests(unittest.TestCase):
    def setUp(self):
        self.library = set(strategy_ids())
        self.router = StrategyRouter(Mock())

    def test_turn_policy_emits_canonicalizable_names(self):
        for message in MESSAGES:
            for previous in PREVIOUS:
                strategy = analyze_teaching_turn(message, previous_strategy=previous).strategy
                self.assertIn(canonical_strategy(strategy), self.library, (message, previous))

    def test_state_policy_emits_canonical_names_only(self):
        for state in STATES:
            policy = select_policy(state)
            self.assertTrue(policy['recommended_strategies'])
            for name in policy['recommended_strategies']:
                self.assertIn(canonical_strategy(name), self.library, name)

    def test_strategy_router_candidates_are_library_ids(self):
        for move in ('question', 'attempt_problematic', 'attempt_partial', 'statement', 'acknowledgement'):
            for state in STATES:
                candidates = self.router._prefilter(move, state, None, None, None)
                self.assertEqual(len(candidates), 3)
                for item in candidates:
                    self.assertIn(item['id'], self.library, item['id'])

    def test_no_path_emits_an_unknown_name(self):
        emitted = set()
        for message in MESSAGES:
            emitted.add(analyze_teaching_turn(message).strategy)
        for state in STATES:
            emitted.update(select_policy(state)['recommended_strategies'])
        for move in ('question', 'attempt_partial'):
            emitted.update(item['id'] for item in self.router._prefilter(move, STATES[0], None, None, None))
        unknown = {name for name in emitted if canonical_strategy(name) not in self.library}
        self.assertEqual(unknown, set())

    def test_legacy_names_stay_accepted(self):
        for name in ('explain', 'contrast', 'break_down', 'feedback', 'progressive_hinting'):
            self.assertIn(canonical_strategy(name), self.library, name)


if __name__ == '__main__':
    unittest.main()
