import unittest
from pathlib import Path

from knowledge.knowledge_units import DEFAULT_INDEX, extract_units, retrieve_units


def _row(text: str, *, chapter_id: int = 3, section_id: int = 1):
    return {
        "chapter_id": chapter_id,
        "section_id": section_id,
        "section": f"{chapter_id}.{section_id} 测试小节",
        "source": "测试教材",
        "page": 1,
        "text": text,
    }


class KnowledgeUnitExtractionTests(unittest.TestCase):
    def test_definition_stops_before_exercise(self):
        units = extract_units([_row(
            "定义3.1 从n个不同元素中取出r个元素的有序排列总数，称为r-排列数。\n"
            "练习3.1 请计算一个与定义无关的排列题。"
        )])

        definition = next(unit for unit in units if unit.kind == "definition")
        self.assertEqual(definition.label, "定义3.1")
        self.assertIn("r-排列数", definition.text)
        self.assertNotIn("练习3.1", definition.text)

    def test_inline_theorem_heading_is_not_treated_as_a_reference(self):
        units = extract_units([_row(
            "定理3.1考虑任意两个有限集合A、B，则并集元素个数由两侧之和减去交集个数确定。\n"
            "练习3.1 练习内容不应进入定理单元。"
        )])

        theorem = next(unit for unit in units if unit.kind == "theorem")
        self.assertEqual(theorem.label, "定理3.1")
        self.assertTrue(theorem.text.startswith("定理3.1考虑"))
        self.assertNotIn("练习3.1", theorem.text)

    def test_inline_reference_after_heading_is_rejected(self):
        units = extract_units([_row(
            "定理3.1与下一节给出的结论等价，这里只是引用。\n"
            "定义3.1 这一段才是真正的定义，具有完整且独立的正文。"
        )])

        self.assertFalse(any(unit.kind == "theorem" for unit in units))
        self.assertTrue(any(unit.kind == "definition" for unit in units))


@unittest.skipUnless(
    Path(DEFAULT_INDEX).is_file(),
    "textbook unit index is not built",
)
class KnowledgeUnitRetrievalTests(unittest.TestCase):
    def test_explicit_number_recalls_the_complete_unit_first(self):
        units = retrieve_units("请说明定理3.1的完整条件和结论。", limit=3)

        self.assertTrue(units)
        self.assertEqual(units[0].kind, "theorem")
        self.assertEqual(units[0].chunk_id, "ch3-s4-theorem-定理3.1")
        self.assertIn("定理3.1", units[0].text)

    def test_new_expressions_recall_canonical_textbook_concepts(self):
        cases = (
            ("选取若干成员时不计先后次序，对应哪类计数？", ("组合",)),
            ("若图的所有边都横跨两个互不相交的顶点组，这是什么图？", ("二分图",)),
            ("连通图中删去一些边后仍连通且无圈，得到什么？", ("生成树",)),
        )
        for question, expected_terms in cases:
            with self.subTest(question=question):
                units = retrieve_units(question, limit=3)
                combined = "\n".join(unit.section + unit.text for unit in units)
                self.assertTrue(any(term in combined for term in expected_terms))

    def test_tree_concept_recalls_the_definition_unit_first(self):
        units = retrieve_units("树的概念", limit=3)
        self.assertTrue(units)
        self.assertEqual(units[0].chunk_id, "ch8-s7-definition-定义8.9")
        self.assertIn("连通无回路的无向图", units[0].text)

    def test_calibration_paraphrases_reach_the_right_section(self):
        cases = (
            ("计算两个集合并集大小时，为什么不能直接相加？", "包含排斥原理"),
            ("两个原子命题至少一个为真时，析取命题的真值怎样确定？", "逻辑联结词"),
        )
        for question, expected_section in cases:
            with self.subTest(question=question):
                units = retrieve_units(question, limit=3)
                self.assertTrue(
                    any(expected_section in unit.section for unit in units),
                    [unit.section for unit in units],
                )


if __name__ == "__main__":
    unittest.main()
