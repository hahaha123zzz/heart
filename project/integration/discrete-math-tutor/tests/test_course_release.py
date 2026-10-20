"""Q2.5：课程发布身份、索引与换版校验。"""
import unittest

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


if __name__ == "__main__":
    unittest.main()
