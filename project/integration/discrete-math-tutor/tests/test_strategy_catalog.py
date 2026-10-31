"""单一策略词表：13 个库 id 为权威，其余都是别名。

目的：防止再出现第 5 份互不一致的教学策略清单（曾同时存在 9/8/13/8 四份）。
"""
import unittest

from agents.adaptive_tutoring import STRATEGIES
from agents.teaching_planner import ALLOWED_STRATEGIES, TeachingPlanner
from agents.teaching_policy import (
    STRATEGY_ALIASES,
    accepted_strategy_names,
    canonical_strategy,
    strategy_ids,
)


class StrategyCatalogTests(unittest.TestCase):
    def test_library_is_the_only_canonical_list(self):
        ids = strategy_ids()
        self.assertEqual(len(ids), 13)
        self.assertEqual(len(set(ids)), 13)
        self.assertNotIn("", ids)

    def test_aliases_never_shadow_canonical_ids(self):
        ids = set(strategy_ids())
        for alias, target in STRATEGY_ALIASES.items():
            self.assertNotIn(alias, ids, f'{alias} 是规范 id，不能同时作别名')
            self.assertIn(target, ids, f'{alias} 指向未知策略 {target}')

    def test_planner_uses_library_ids(self):
        self.assertEqual(ALLOWED_STRATEGIES, strategy_ids())
        self.assertEqual(set(ALLOWED_STRATEGIES), set(strategy_ids()))

    def test_runtime_names_all_normalize(self):
        ids = set(strategy_ids())
        for name in STRATEGIES:
            self.assertIn(canonical_strategy(name), ids, f'{name} 未归一到库 id')

    def test_accepted_names_cover_canonical_and_alias(self):
        accepted = set(accepted_strategy_names())
        self.assertTrue(set(strategy_ids()) <= accepted)
        self.assertTrue(set(STRATEGY_ALIASES) <= accepted)

    def test_canonical_is_idempotent(self):
        for name in strategy_ids():
            self.assertEqual(canonical_strategy(name), name)
        self.assertEqual(canonical_strategy("explain"), "direct_explanation")
        self.assertEqual(canonical_strategy("not_a_strategy"), "not_a_strategy")

    def test_planner_normalizes_alias_and_rejects_unknown(self):
        policy = {"recommended_strategies": ["conceptual_comparison"], "action": "explain",
                  "difficulty": "medium", "hint_level": 1}
        plan = TeachingPlanner._validate({"strategy": "progressive_hinting"}, policy)
        self.assertEqual(plan.strategy, "hint")
        plan = TeachingPlanner._validate({"strategy": "bogus"}, policy)
        self.assertEqual(plan.strategy, "conceptual_comparison")
        self.assertIn(plan.strategy, ALLOWED_STRATEGIES)

    def test_no_dead_strategy_list_returns(self):
        import agents.teaching_policy as policy
        self.assertFalse(hasattr(policy, "KNOWN_STRATEGIES"))


if __name__ == "__main__":
    unittest.main()
