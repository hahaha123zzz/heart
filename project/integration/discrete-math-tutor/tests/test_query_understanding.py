import unittest

from knowledge.query_understanding import understand


class QueryUnderstandingTests(unittest.TestCase):
    def assert_resolves(self, question: str, expected: str):
        result = understand(question)
        titles = [candidate.title for candidate in result.candidates]
        self.assertTrue(any(expected in title for title in titles), titles)
        self.assertIn("教材结构候选", result.retrieval_query)

    def test_named_concepts_resolve_to_specific_sections(self):
        cases = (
            ("一个集合的幂集由哪些集合组成？", "幂集运算"),
            ("图中的一个顶点的度是怎样定义的？", "结点的度"),
            ("二分图的顶点集合具有什么特点？", "二分图的基本概念"),
            ("一个关系成为等价关系必须满足哪些性质？", "等价关系与等价类"),
            ("函数 f:A→B 什么时候是满射？", "单射的、满射的和双射"),
            ("两个有限集合的包含排斥公式怎么写？", "包含排斥原理"),
            ("主析取范式由哪一类项组成？", "主析取范式与主合取范式"),
            ("量词的辖域在谓词公式中指什么范围？", "量词及其辖域"),
            ("一棵有 n 个顶点的树有多少条边？", "树的基本概念"),
        )
        for question, expected in cases:
            with self.subTest(question=question):
                self.assert_resolves(question, expected)

    def test_unseen_paraphrase_does_not_invent_a_section(self):
        result = understand("股票市场明天会涨吗？")
        self.assertEqual(result.candidates, ())
        self.assertEqual(result.retrieval_query, "股票市场明天会涨吗？")

    def test_textbook_concept_inference_handles_missing_title_words(self):
        subset_count = understand("含三个元素的集合一共有多少个子集？")
        self.assertIn("幂集", subset_count.related_concepts)
        self.assertIn("幂集运算", subset_count.candidates[0].title)

        contradiction = understand("那矛盾式对任何指派都取什么真值？")
        self.assertIn("重言式", contradiction.related_concepts)
        self.assertIn("重言式", contradiction.candidates[0].title)

    def test_plain_combination_is_not_confused_with_multisets(self):
        result = understand("从 n 个不同元素中取 r 个的组合数公式是什么？")
        self.assertIn("组合的计数", result.candidates[0].title)
        self.assertNotIn("重集", result.candidates[0].title)

    def test_ambiguous_or_empty_question_requests_a_specific_object(self):
        result = understand("为什么会这样？")
        self.assertTrue(result.needs_clarification)
        self.assertIn("具体名称", result.clarification)


if __name__ == "__main__":
    unittest.main()
