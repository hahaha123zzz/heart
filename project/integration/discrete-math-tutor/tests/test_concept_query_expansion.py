import unittest

from knowledge.concept_aliases import clean_query, expand_query


class ConceptQueryExpansionTests(unittest.TestCase):
    def test_question_scaffolding_is_removed_without_losing_the_subject(self):
        self.assertEqual(
            clean_query("动量守恒定律适用于什么条件？"),
            "动量守恒定律",
        )
        self.assertEqual(
            clean_query("怎样判断一个映射是否单射？"),
            "判断一个映射单射",
        )

    def test_structural_terms_cover_conjunction_tree_and_composition(self):
        conjunction = expand_query("A∧B 在什么条件下取真？")
        tree = expand_query("连通无圈图为何是一棵树？")
        composition = expand_query("函数复合 f○g 的应用次序是什么？")
        self.assertIn("合取", conjunction)
        self.assertIn("第8章 8.3.1 树的基本概念", tree)
        self.assertIn("函数的合成", composition)

    def test_unrelated_question_gets_no_in_scope_expansion(self):
        expanded = expand_query("股票的市盈率如何用于估值？")
        self.assertEqual(expanded, "股票的市盈率用于估值")
        self.assertNotIn("教材术语", expanded)


if __name__ == "__main__":
    unittest.main()
