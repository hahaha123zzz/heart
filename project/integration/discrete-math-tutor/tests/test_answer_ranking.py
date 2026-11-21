import unittest

from knowledge.answer_ranking import rank_excerpt_sentences


class AnswerRankingTests(unittest.TestCase):
    def test_definition_question_skips_intro_and_selects_answer_sentence(self):
        ranked = rank_excerpt_sentences(
            "命题的否定与原命题在真值上有什么关系？",
            [(1, "逻辑联结词", (
                "本节介绍逻辑联结词的基本内容。"
                "设p表示一命题，那么┐p表示命题p的否定。"
                "p真时┐p假，而p假时┐p真。"
            ))],
        )
        self.assertIn("p真时┐p假", ranked[0][2])

    def test_condition_question_prefers_if_and_only_if_sentence(self):
        ranked = rank_excerpt_sentences(
            "A∧B 在什么条件下取真？",
            [(1, "逻辑联结词", (
                "本节介绍合取词。"
                "p∧q为真，当且仅当p和q都真。"
            ))],
        )
        self.assertIn("当且仅当", ranked[0][2])

    def test_antisymmetry_question_prefers_definition_over_example_with_topic_words(self):
        ranked = rank_excerpt_sentences(
            "一个关系什么时候具有反对称性？",
            [(1, "关系的基本特性", (
                "整数集合上的整除关系无反对称性。"
                "称R是反对称的，如果对任意x,y，xRy且yRx蕴涵x=y。"
            ))],
        )
        self.assertIn("称R是反对称的", ranked[0][2])

    def test_negation_question_prefers_truth_flip_over_distractor_relation(self):
        ranked = rank_excerpt_sentences(
            "命题的否定与原命题在真值上有什么关系？",
            [(1, "逻辑联结词", (
                "蕴涵词不要求p和q有什么关系。"
                "设p表示命题，p真时┐p假，而p假时┐p真。"
            ))],
        )
        self.assertIn("p真时┐p假", ranked[0][2])

    def test_ordered_pair_question_prefers_component_definition(self):
        ranked = rank_excerpt_sentences(
            "有序对 (a,b) 与 (b,a) 一定相等吗？",
            [(1, "集合的笛卡儿积", (
                "有序对由第一分量和第二分量组成，两个有序对相等要求对应分量分别相等。"
                "序关系中的边可以写作(a,b)。"
            ))],
        )
        self.assertIn("第一分量", ranked[0][2])


if __name__ == "__main__":
    unittest.main()
