"""Natural-question preset matching: topic + evidence, not a full-word whitelist."""
import unittest
from unittest.mock import patch

from agents.task_execution import TaskExecution
from knowledge.textbook import TextbookChunk
from visualization.psychology_presets import match_topic


def material(chapter, section, text="教材原文"):
    return TextbookChunk("chapter.txt", f"第{section}节", text, frozenset(),
                         chapter_id=chapter, section_id=section)


class NaturalPresetTests(unittest.TestCase):
    def match(self, question, reply, chapter, section):
        with patch("visualization.psychology_presets.document_for_chapter",
                   return_value={"source": "chapter.txt"}):
            return match_topic(question, reply, [material(chapter, section)],
                               TaskExecution(learning_intents=["explain"]))

    def test_between_within_design_natural_question(self):
        question = "比较被试内设计与被试间设计，说明各自适用条件和容易混淆的地方"
        reply = "被试内设计是每名被试接受全部处理水平；被试间设计是每名被试只接受一个水平。"
        self.assertEqual(self.match(question, reply, 5, 1), "designs")

    def test_signal_detection_natural_question(self):
        question = "解释信号检测论里的辨别力和判准，它们分别受什么影响"
        reply = "信号检测论用辨别力和判准描述信号与噪声的区分。"
        self.assertEqual(self.match(question, reply, 7, 3), "signal_detection")

    def test_spatial_cue_natural_question(self):
        question = "空间线索实验中，有效线索和无效线索条件下注意是怎样分配的"
        reply = "空间线索实验比较有效线索与无效线索条件下的注意分配。"
        self.assertEqual(self.match(question, reply, 9, 2), "spatial_cue")

    def test_simple_definition_and_custom_experiment_do_not_match(self):
        reply = "自变量是研究者操纵的变量，因变量是观察的变量。"
        for question in (
            "什么是自变量？",
            "我的实验中学习方法是自变量，成绩是因变量，设计是否正确？",
            "第2章第10页的自变量和因变量是什么？",
            "请用做饭例子解释自变量和因变量",
            "不要图解，解释自变量和因变量",
        ):
            with self.subTest(question=question):
                self.assertIsNone(self.match(question, reply, 2, 2))

    def test_generic_diagram_suffix_keeps_preset(self):
        question = "请解释自变量和因变量，请结合教材和图解说明"
        reply = "自变量是研究者操纵的变量，因变量是观察的变量。"
        self.assertEqual(self.match(question, reply, 2, 2), "variables")


if __name__ == "__main__":
    unittest.main()
