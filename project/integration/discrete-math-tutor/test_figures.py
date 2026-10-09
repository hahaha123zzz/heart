"""图片引用的离线检查；无需启动模型或数据库。"""

from __future__ import annotations

import hashlib
import base64
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from knowledge import figures
from knowledge.textbook import load_textbook, retrieve
from llm.client import LLMClient, LLMError


class FigureCatalogTests(unittest.TestCase):
    def tearDown(self) -> None:
        figures.load_figures.cache_clear()

    def test_verified_figure_is_retrieved_and_unrelated_query_is_not(self) -> None:
        figure = figures.get_figure("figure-7-20")
        self.assertIsNotNone(figure)
        self.assertEqual(figures.section_figures(7, 8)[0]["image_url"],
                         "/api/figures/figure-7-20/image")
        self.assertEqual([f.id for f in figures.retrieve_figures("图7.20", [])],
                         ["figure-7-20"])
        self.assertEqual([f.id for f in figures.retrieve_figures("图7.8", [])],
                         ["figure-7-8"])
        self.assertEqual([f.id for f in figures.retrieve_figures("图7.23", [])],
                         ["figure-7-23"])
        self.assertEqual([f["id"] for f in figures.section_figures(7, 4)],
                         ["figure-7-8"])
        self.assertEqual([f["id"] for f in figures.section_figures(7, 8)],
                         ["figure-7-20", "figure-7-23"])
        sources = retrieve("哈密顿图和正十二面体", load_textbook())
        self.assertEqual([f.id for f in figures.retrieve_figures(
            "哈密顿图和正十二面体", sources)], ["figure-7-20"])
        self.assertEqual(figures.retrieve_figures("集合是什么", retrieve(
            "集合是什么", load_textbook())), [])
        self.assertIsNone(figures.get_figure("../../secrets"))

    def test_unapproved_and_modified_assets_are_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            asset_dir = root / "assets"
            asset_dir.mkdir()
            data = b"test PNG placeholder"
            (asset_dir / "figure.png").write_bytes(data)
            entry = {
                "id": "figure-1-1", "label": "图1.1", "chapter_id": 1,
                "section_id": 1, "source": "第1章.doc", "caption": "测试",
                "context": "测试", "filename": "figure.png",
                "sha256": hashlib.sha256(data).hexdigest(),
                "review_status": "pending",
            }
            catalog = root / "catalog.json"
            with patch.object(figures, "ASSET_DIR", asset_dir), patch.object(
                figures, "CATALOG_PATH", catalog
            ), patch.object(figures, "EXTRACTED_CATALOG_PATH", root / "missing.json"):
                catalog.write_text(json.dumps([entry]), encoding="utf-8")
                figures.load_figures.cache_clear()
                self.assertEqual(figures.load_figures(), ())
                entry["review_status"] = "approved"
                entry["sha256"] = "0" * 64
                catalog.write_text(json.dumps([entry]), encoding="utf-8")
                figures.load_figures.cache_clear()
                self.assertEqual(figures.load_figures(), ())

    def test_vision_request_sends_only_approved_image_to_vision_model(self) -> None:
        requests = []

        def create(**kwargs):
            requests.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content="图中显示一条加粗的回路。"),
                finish_reason="stop",
            )])

        client = LLMClient(api_key="test-key", mock=False)
        client._client = SimpleNamespace(chat=SimpleNamespace(
            completions=SimpleNamespace(create=create)
        ))
        messages = [{"role": "user", "content": "请看教材图7.20"}]
        image_path = figures.get_figure("figure-7-20").path
        self.assertIn("回路", client.chat(messages, image_paths=[image_path]))
        self.assertEqual(requests[0]["model"], client.vision_model)
        parts = requests[0]["messages"][-1]["content"]
        self.assertEqual(parts[0], {"type": "text", "text": "请看教材图7.20"})
        encoded = parts[1]["image_url"]["url"].split(",", 1)[1]
        self.assertEqual(base64.b64decode(encoded), image_path.read_bytes())
        self.assertEqual(messages[-1]["content"], "请看教材图7.20")
        client.chat(messages)
        self.assertEqual(requests[1]["model"], client.model)
        self.assertIsInstance(requests[1]["messages"][-1]["content"], str)

    def test_vision_request_rejects_unapproved_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "private.png"
            path.write_bytes(b"not a textbook figure")
            with self.assertRaises(LLMError):
                LLMClient._with_images([{"role": "user", "content": "描述图"}], [path])

    def test_cached_figure_is_rejected_after_file_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            asset_dir = root / "assets"
            asset_dir.mkdir()
            path = asset_dir / "figure.png"
            path.write_bytes(b"original image")
            catalog = root / "catalog.json"
            catalog.write_text(json.dumps([{
                "id": "figure-1-1", "label": "图1.1", "chapter_id": 1,
                "section_id": 1, "source": "第1章.doc", "caption": "测试",
                "context": "测试", "filename": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "review_status": "approved",
            }]), encoding="utf-8")
            with patch.object(figures, "ASSET_DIR", asset_dir), patch.object(
                figures, "CATALOG_PATH", catalog
            ):
                figures.load_figures.cache_clear()
                self.assertIsNotNone(figures.get_figure("figure-1-1"))
                path.write_bytes(b"replaced image")
                self.assertIsNone(figures.get_figure("figure-1-1"))
                with self.assertRaises(LLMError):
                    LLMClient._with_images(
                        [{"role": "user", "content": "描述图"}], [path]
                    )


if __name__ == "__main__":
    unittest.main()
