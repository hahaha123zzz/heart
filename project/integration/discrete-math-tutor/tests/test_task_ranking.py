"""任务偏好不能改变章节归属、明确编号或证据资格。"""
import unittest

from agents.task_execution import TaskExecution
from knowledge.hybrid_retrieval import _primary_unit
from knowledge.task_ranking import prefer_task_units, unit_types


def row(key, text, section=1, chapter=1, kind="text"):
    return {"id": key, "text": text, "section_id": section, "chapter_id": chapter, "kind": kind}


class TaskRankingTests(unittest.TestCase):
    def rank(self, rows, preferred=("example",), refs=()):
        ranked = [(10 - i, r) for i, r in enumerate(rows)]
        return [r["id"] for _, r in prefer_task_units(ranked, preferred,
                is_primary=lambda r: _primary_unit(r, set(refs)))]

    def test_example_moves_within_section_without_promoting_other_chapter(self):
        rows = [row("body", "集合的运算"), row("other", "例2.1 鸽笼", chapter=2),
                row("example", "例1.1 集合的运算")]
        self.assertEqual(self.rank(rows), ["example", "other", "body"])

    def test_explicit_theorem_stays_ahead_of_example(self):
        rows = [row("theorem", "定理1.2 集合交换律"), row("body", "集合的运算"),
                row("example", "例1.1 集合运算")]
        self.assertEqual(self.rank(rows, refs=("定理1.2",)), ["theorem", "example", "body"])

    def test_missing_section_and_resource_are_not_inferred_as_examples(self):
        rows = [row("legacy", "集合", section=None), row("example", "例1.1 集合", section=None)]
        self.assertEqual(self.rank(rows), ["legacy", "example"])
        self.assertEqual(unit_types(row("image", "定义1.1 图", kind="image_context")), frozenset())

    def test_proof_body_is_recognized_but_background_mention_is_not(self):
        self.assertIn("proof", unit_types(row("proof", "定理7.4 路径\n证 不失一般性")))
        self.assertNotIn("proof", unit_types(row("background", "这里引用证明的结论。")))

    def test_hint_and_comparison_keep_default_ranking(self):
        for intents, constraints in ((["hint", "proof"], []), (["compare", "example"], []),
                                     (["proof"], ["no_full_answer"]), ([], [])):
            task = TaskExecution(learning_intents=intents, answer_constraints=constraints)
            self.assertEqual(task.retrieval_types(), ())

    def test_explicit_definition_and_ordered_example_proof_preferences(self):
        self.assertEqual(TaskExecution(learning_intents=["explain"], retrieval_query="交集是什么？").retrieval_types(), ("definition",))
        self.assertEqual(TaskExecution(learning_intents=["example", "proof"]).retrieval_types(), ("example", "theorem", "proof"))

    def test_unknown_preference_cannot_change_order(self):
        self.assertEqual(self.rank([row("a", "正文"), row("b", "例1.1 集合")], ("arbitrary",)), ["a", "b"])


if __name__ == "__main__":
    unittest.main()
