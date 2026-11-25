"""固定教材导入复用启动期摘要，避免每轮重读全部 PDF。"""
import hashlib
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from integrations.deeptutor import course_reading
from knowledge import fixed_book
from knowledge import pdf_reader  # 先完成模块导入，避免测试替换教材目录影响 manifest 加载


class CourseReadingStartupDigestTests(unittest.TestCase):
    def _record(self, path):
        return {"document_id": "doc-1", "chapter_id": 1, "title": "第一章", "pages": [],
                "version": hashlib.sha256(path.read_bytes()).hexdigest()}

    def test_fixed_textbook_uses_startup_digest_without_rehashing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "chapter_01.generated.pdf"
            path.write_bytes(b"frozen at startup")
            record = self._record(path)
            state = SimpleNamespace(ready=True, source_root=root,
                                    hashes={str(path.resolve()): record["version"]})
            with (patch.dict("os.environ", FIXED_BOOK_RETRIEVAL_ENABLED="1"),
                  patch.object(fixed_book, "runtime", state),
                  patch("knowledge.course_config.PSYCHOLOGY_DIR", root),
                  patch("knowledge.pdf_reader.documents", return_value=[record]),
                  patch("knowledge.pdf_reader.pdf_path", return_value=path),
                  patch.object(course_reading, "file_digest",
                               side_effect=AssertionError("不应重读整份教材"))):
                _, _, rows = course_reading._course_documents()
        self.assertEqual(rows[0]["version"], record["version"])

    def test_fixed_textbook_version_still_checked_without_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "chapter_01.generated.pdf"
            path.write_bytes(b"actual bytes")
            record = self._record(path) | {"version": "0" * 64}
            with (patch("knowledge.course_config.PSYCHOLOGY_DIR", root),
                  patch("knowledge.pdf_reader.documents", return_value=[record]),
                  patch("knowledge.pdf_reader.pdf_path", return_value=path)):
                with self.assertRaisesRegex(ValueError, "版本不一致"):
                    course_reading._course_documents()


if __name__ == "__main__":
    unittest.main()
