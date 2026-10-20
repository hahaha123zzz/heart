"""Q2.4/Q2.5：原图资产映射、哈希校验与缺口报告。"""
import hashlib
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image
from knowledge import figures, source_visuals
from knowledge.textbook import TextbookChunk


class SourceVisualTests(unittest.TestCase):
    def tearDown(self):
        source_visuals.clear_cache()
        figures.load_figures.cache_clear()

    def test_real_assets_are_bound_to_sections_and_figure_numbers(self):
        stats = source_visuals.stats()
        if not stats["total"]:
            self.skipTest("当前工作区没有未跟踪的心理学原图资产")
        self.assertGreaterEqual(stats["total"], 1)
        visual = next(visual for visual in source_visuals.load_visuals()[0]
                      if visual.section_id and visual.is_valid())
        self.assertTrue(visual.is_valid())
        self.assertIn(visual, source_visuals.visuals_for_section(visual.chapter_id, visual.section_id))
        self.assertEqual(visual.public()["image_url"], f"/api/figures/{visual.id}/image")
        self.assertIn(visual.id, [item["id"] for item in figures.section_figures(
            visual.chapter_id, visual.section_id)])

    def test_jpeg_source_visual_keeps_its_real_mime_type(self):
        visuals = [visual for visual in source_visuals.load_visuals()[0]
                   if visual.path.suffix.lower() in (".jpg", ".jpeg")]
        if not visuals:
            self.skipTest("当前工作区没有 JPEG 原图资产")
        from llm.client import LLMClient
        parts = LLMClient._with_images([{"role": "user", "content": "看图"}], [visuals[0].path])
        url = parts[-1]["content"][1]["image_url"]["url"]
        self.assertTrue(url.startswith("data:image/jpeg;base64,"))

    def test_missing_and_stale_assets_are_reported_not_silently_used(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            chapter = root / "chapters" / "chapter_01"
            (chapter / "assets").mkdir(parents=True)
            image = chapter / "assets" / "image-01-0001.png"
            Image.new("RGB", (400, 300), "white").save(image)
            (chapter / 'source.docx').write_bytes(b'original-source')
            source_sha = hashlib.sha256(b'original-source').hexdigest()
            (root / "manifest.json").write_text(json.dumps({
                "full_import": {"chapters": [{"chapter_id": 1, "source_sha256": source_sha,
                    "docx": "chapters/chapter_01/source.docx"}]}}),
                encoding="utf-8")
            entry = {
                "id": "image-01-0001", "kind": "image", "chapter_id": 1,
                "section_id": 1, "block_index": 0, "source": "第1章.docx",
                "source_sha256": source_sha, "filename": "assets/image-01-0001.png",
                "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                "labels": ["图1.1"], "context": "教材原图", "section": "第一节",
                "review_status": "pending", "occurrences": [{"block": 0}],
            }
            assets = chapter / "assets.json"
            assets.write_text(json.dumps([entry]), encoding="utf-8")
            with patch.object(source_visuals, "PSYCHOLOGY_DIR", root), \
                    patch("knowledge.course_config.PSYCHOLOGY", True):
                source_visuals.clear_cache()
                figures.load_figures.cache_clear()
                loaded = source_visuals.load_visuals()[0]
                self.assertEqual([item.id for item in loaded], ["image-01-0001"])
                self.assertEqual([item["id"] for item in figures.section_figures(1, 1)],
                                 ["image-01-0001"])
                self.assertEqual([item.id for item in figures.retrieve_figures("图1.1", [])],
                                 ["image-01-0001"])
                source = TextbookChunk("第1章.docx", "第一节", "教材正文", frozenset(),
                                       chapter_id=1, section_id=1, asset_ids=("image-01-0001",))
                self.assertEqual(figures.retrieve_figures("解释这个概念", [source]), [])
                self.assertEqual([item.id for item in figures.retrieve_figures("图1.1", [source])],
                                 ["image-01-0001"])
                cached_figure = figures.get_figure('image-01-0001')
                self.assertTrue(cached_figure.is_valid())
                entry['section_id'] = 2
                assets.write_text(json.dumps([entry]), encoding='utf-8')
                self.assertFalse(loaded[0].is_valid())
                self.assertFalse(cached_figure.is_valid())
                entry['section_id'] = 1
                assets.write_text(json.dumps([entry]), encoding='utf-8')
                original_source = chapter / 'source.docx'
                original_source.write_bytes(b'changed-edition')
                self.assertFalse(loaded[0].is_valid())
                self.assertFalse(cached_figure.is_valid())
                original_source.write_bytes(b'original-source')
                image.unlink()
                source_visuals.clear_cache()
                figures.load_figures.cache_clear()
                self.assertEqual(source_visuals.load_visuals()[0], ())
                self.assertIn("原图文件缺失",
                              [gap["reason"] for gap in source_visuals.gaps()])
                entry["source_sha256"] = "b" * 64
                image.write_bytes(b"real source image")
                entry["sha256"] = hashlib.sha256(image.read_bytes()).hexdigest()
                assets.write_text(json.dumps([entry]), encoding="utf-8")
                source_visuals.clear_cache()
                figures.load_figures.cache_clear()
                self.assertEqual(source_visuals.load_visuals()[0], ())
                self.assertIn("原教材源文件哈希与当前发布清单不一致",
                              [gap["reason"] for gap in source_visuals.gaps()])
                entry["source_sha256"] = source_sha
                Image.new("RGB", (1688, 58), "white").save(image)
                entry["sha256"] = hashlib.sha256(image.read_bytes()).hexdigest()
                assets.write_text(json.dumps([entry]), encoding="utf-8")
                source_visuals.clear_cache()
                figures.load_figures.cache_clear()
                self.assertEqual(source_visuals.load_visuals()[0], ())
                self.assertIn("占位/缺图资产尺寸异常，不作为教材原图",
                              [gap["reason"] for gap in source_visuals.gaps()])


if __name__ == "__main__":
    unittest.main()
