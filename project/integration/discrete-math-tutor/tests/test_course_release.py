"""Q2.5：课程发布身份、索引与换版校验。"""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from knowledge import course_release


class CourseReleaseTests(unittest.TestCase):
    def setUp(self):
        course_release.clear_cache()

    def tearDown(self):
        course_release.clear_cache()

    def test_release_identity_binds_chapters_index_and_visuals(self):
        state = course_release.snapshot()
        self.assertEqual(state["course_id"], "experimental-psychology-3")
        self.assertEqual(len(state["chapters"]), 11)
        self.assertTrue(all(chapter["pdf_sha256"] for chapter in state["chapters"]))
        self.assertTrue(state["index_sha256"])
        self.assertEqual(len(state["release_id"]), 64)
        self.assertIn("visuals", state)
        # 当前清单明确是 staging，且原图待审核；不能把文件齐全冒充已发布。
        self.assertFalse(state["ready"])
        self.assertTrue(any("staging" in gap for gap in state["gaps"]))
        self.assertIn(state["release_id"], course_release.binding()["release_id"])

    def test_changed_release_identity_is_rejected(self):
        state = course_release.snapshot()
        self.assertEqual(course_release.validate(state)["release_id"], state["release_id"])
        with self.assertRaisesRegex(ValueError, "发布版本已变化"):
            course_release.validate({"release_id": "0" * 64})

    def test_index_identity_falls_back_to_the_verified_legacy_pin(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            pinned = "a" * 64
            with patch.object(course_release, "PSYCHOLOGY_DIR", root):
                self.assertEqual(course_release.index_identity(),
                                 (None, "检索索引 rag_index.sqlite3 缺失"))
                (root / "retrieval_identity.json").write_text(
                    json.dumps({"legacy_index_sha256": pinned}), encoding="utf-8")
                self.assertEqual(course_release.index_identity(), (pinned, None))
                (root / "rag_index.sqlite3").write_bytes(b"index")
                actual, gap = course_release.index_identity()
                self.assertIsNone(gap)
                self.assertEqual(actual, course_release._sha256(root / "rag_index.sqlite3"))
                self.assertNotEqual(actual, pinned)


if __name__ == "__main__":
    unittest.main()
