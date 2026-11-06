import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agents.q3_navigation import LearningTarget
from agents.q3_tools import LookupFiguresTool, build_registry
from agents.tool_protocol import ToolContext
from knowledge.visual_index import clear_cache, load_index, parse_index
from scripts.build_visual_index import chapter_candidates, merge_drafts

INDEX = """# 测试索引
## 第3章 相关设计和准实验设计
### 第1节 相关设计
#### 图
- 图3-1｜曲线图｜p.3｜耶克斯-道德森定律示意图｜知识点: 曲线相关、最佳唤醒水平｜内容: 倒U形曲线，中等唤醒时效率最高｜用于: 解释曲线相关｜asset_id: image-03-0003｜状态: 已核对
- 图3-2｜散点图｜p.4｜零相关｜知识点: 零相关、相关系数｜内容: 散点无线性趋势｜用于: 解释零相关｜asset_id: image-03-0005｜状态: 已核对
- 图3-9｜流程图｜p.20｜缺图示例｜知识点: 时间系列设计｜内容: 原图缺失，仅有文字说明｜用于: 说明时间系列｜状态: 缺图
#### 表
- 表-｜数据表｜p.6｜10名儿童命名物体数量｜知识点: 积差相关｜内容: 年龄与命名数量两列｜用于: 演示积差相关计算｜blocks: 73｜状态: 已核对
### 第2节 准实验设计
#### 图
- 图3-10｜曲线图｜p.27｜改变工时后的生产效率｜知识点: 时间系列设计、生产效率｜内容: 阶段变化曲线｜用于: 说明时间系列应用｜asset_id: image-03-0020｜状态: 已核对
## 第6章 单被试设计
### 第2节 A-B-A设计
#### 图
- 图6-10｜示意图｜p.5｜A-B-A设计流程｜知识点: A-B-A设计｜内容: 基线-处理-撤销三阶段｜用于: 解释A-B-A设计｜asset_id: image-06-0015｜状态: 已核对
"""


class VisualIndexTests(unittest.TestCase):
    def setUp(self):
        self.index = parse_index(INDEX)

    def test_parse_keeps_section_and_unnumbered_table(self):
        self.assertEqual(len(self.index.entries), 6)
        self.assertEqual([entry.label for entry in self.index.entries if entry.section_id == 1],
                         ["图3-1", "图3-2", "图3-9", "表-"])
        self.assertIsNone(next(entry for entry in self.index.entries if entry.label == "图3-9").asset_id)

    def test_lookup_defaults_to_current_section_only(self):
        entries = self.index.lookup(chapter_id=3, section_id=1, query="")
        self.assertEqual({entry.label for entry in entries}, {"图3-1", "图3-2", "图3-9", "表-"})
        self.assertNotIn("图3-10", {entry.label for entry in entries})

    def test_lookup_explicit_figure_crosses_sections(self):
        entries = self.index.lookup(chapter_id=3, section_id=1, query="图6-10是什么")
        self.assertEqual([entry.label for entry in entries], ["图6-10"])

    def test_lookup_empty_section_does_not_fall_back(self):
        self.assertEqual(self.index.lookup(chapter_id=3, section_id=9, query=""), [])

    def test_lookup_section_without_chapter_does_not_mix(self):
        self.assertEqual(self.index.lookup(chapter_id=None, section_id=1, query=""), [])

    def test_lookup_global_query_finds_matching_entry(self):
        entries = self.index.lookup(chapter_id=None, section_id=None, query="零相关")
        self.assertEqual(entries[0].label, "图3-2")

    def test_lookup_falls_back_to_same_chapter_when_section_has_no_match(self):
        entries = self.index.lookup(chapter_id=3, section_id=1, query="改变工时")
        self.assertEqual(entries[0].label, "图3-10")

    def test_lookup_query_prefers_matching_entry(self):
        entries = self.index.lookup(chapter_id=3, section_id=1, query="零相关")
        self.assertEqual(entries[0].label, "图3-2")


class LookupFiguresToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "index.md"
        self.path.write_text(INDEX, encoding="utf-8")
        self.target = LearningTarget(target_id="t", name="相关设计", chapter_id=3, section_id=1)
        self.context = ToolContext(student_id="s", session_id="x",
                                   state={"learning_target": self.target})
        self.patch = patch("knowledge.visual_index.INDEX_PATH", self.path)
        self.patch.start()
        clear_cache()

    def tearDown(self):
        self.patch.stop()
        clear_cache()
        self.temp.cleanup()

    def test_tool_returns_only_current_section(self):
        result = LookupFiguresTool().run({"query": ""}, self.context)
        self.assertTrue(result.success)
        self.assertIn("图3-1", result.content)
        self.assertIn("表-", result.content)
        self.assertNotIn("图3-10", result.content)

    def test_tool_returns_named_figure_outside_section(self):
        result = LookupFiguresTool().run({"query": "图6-10"}, self.context)
        self.assertTrue(result.success)
        self.assertIn("图6-10", result.content)

    def test_tool_without_target_or_chapter_fails(self):
        context = ToolContext(student_id="s", session_id="x", state={})
        result = LookupFiguresTool().run({}, context)
        self.assertFalse(result.success)

    def test_tool_global_query_without_target(self):
        context = ToolContext(student_id="s", session_id="x", state={})
        result = LookupFiguresTool().run({"query": "零相关"}, context)
        self.assertTrue(result.success)
        self.assertIn("图3-2", result.content)

    def test_registry_mounts_lookup_for_psychology(self):
        with patch("knowledge.course_config.PSYCHOLOGY", True):
            registry = build_registry(allow_skills=False)
        self.assertIn("lookup_figures", registry.names())

    def test_registry_omits_lookup_for_non_psychology(self):
        with patch("knowledge.course_config.PSYCHOLOGY", False):
            registry = build_registry(allow_skills=False)
        self.assertNotIn("lookup_figures", registry.names())

    def test_prompt_mentions_lookup_when_mounted(self):
        from agents.loop_prompts import build_loop_system_prompt
        prompt = build_loop_system_prompt(target=self.target,
                                          definitions=[LookupFiguresTool().definition])
        self.assertIn("lookup_figures", prompt)
        self.assertIn("缺图", prompt)
        self.assertIn("待核", prompt)


class CaptionRetrievalTests(unittest.TestCase):
    def test_caption_source_attaches_verified_figure_without_query_cue(self):
        from knowledge.figures import retrieve_figures
        from knowledge.textbook import TextbookChunk, terms_for
        text = "图1-4　科学研究过程:从研究思想到结果报告"
        chunk = TextbookChunk(source="第1章实验心理学概论.txt", section="第三节 心理学实验的程序",
                              text=text, terms=terms_for(text), chapter_id=1, section_id=3)
        figures = retrieve_figures("给我解释一下科学研究过程", [chunk])
        self.assertEqual([figure.id for figure in figures], ["image-01-0006"])

    def test_no_caption_and_no_cue_still_returns_nothing(self):
        from knowledge.figures import retrieve_figures
        from knowledge.textbook import TextbookChunk, terms_for
        text = "科学研究的过程和结果应该是可以重复的。"
        chunk = TextbookChunk(source="第1章实验心理学概论.txt", section="第三节 心理学实验的程序",
                              text=text, terms=terms_for(text), chapter_id=1, section_id=3)
        self.assertEqual(retrieve_figures("给我解释一下科学研究过程", [chunk]), [])


class CandidateBuilderTests(unittest.TestCase):
    def test_chapter_three_marks_placeholder_and_groups_continuation(self):
        data = chapter_candidates(3)
        images = {image["id"]: image for image in data["images"]}
        self.assertFalse(images["image-03-0002"]["candidate"])
        self.assertTrue(images["image-03-0003"]["caption"].startswith("图3-1"))
        table = next(item for item in data["tables"] if item["caption"].startswith("表3-1"))
        self.assertEqual(table["blocks"], [18, 20])

    def test_merge_orders_sections_even_if_draft_starts_late(self):
        with tempfile.TemporaryDirectory() as root:
            drafts = Path(root) / "drafts"
            drafts.mkdir()
            (drafts / "chapter_03.md").write_text(
                "### 第二节 准实验设计\n#### 表\n"
                "- 表3-9｜对照表｜p.19｜准实验与真实验的区别｜知识点: 准实验设计｜"
                "内容: 对比内部效度与外部效度｜用于: 区分两种设计｜blocks: 247｜状态: 已核对\n",
                encoding="utf-8")
            out = Path(root) / "index.md"
            result = merge_drafts(drafts, out)
            text = out.read_text(encoding="utf-8")
            self.assertEqual(result["entries"], 1)
            self.assertLess(text.index("### 第1节"), text.index("### 第2节"))
            self.assertIn("### 第2节 准实验设计", text)
            self.assertNotIn("第二节 准实验设计", text)

    def test_checked_in_index_has_no_missing_captions(self):
        from scripts.build_visual_index import INDEX_PATH, validate_index
        result = validate_index(INDEX_PATH)
        self.assertEqual(result["errors"], [])
        self.assertGreater(result["entries"], 200)


if __name__ == "__main__":
    unittest.main()

