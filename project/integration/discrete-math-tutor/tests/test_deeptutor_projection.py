"""教材版本与来源适配保持原坐标，不把教学正文写入事件投影。"""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from integrations.deeptutor.task_projection import projection_for, source_pointers
from integrations.deeptutor.turn_contract import SourceRect


class SourceProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "published.pdf"
        self.path.write_bytes(b"published textbook fixture")
        self.version = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.record = {"document_id": "published-chapter", "chapter_id": 1, "version": self.version}
        self.rects = [{"page": page, "x1": .1, "y1": .2, "x2": .9, "y2": .3} for page in (1, 2)]
        self.payload = {"message": "学生的问题", "selection": {"document_id": "published-chapter", "version": self.version,
            "kind": "text", "text": "浏览器预览文字", "rects": self.rects}, "reader_location": {"chapter_id": 1, "section_id": 1}}
        self.patches = [patch("knowledge.pdf_reader.document", return_value=self.record),
                        patch("knowledge.pdf_reader.documents", return_value=[self.record]),
                        patch("knowledge.pdf_reader.document_for_chapter", return_value=self.record),
                        patch("knowledge.pdf_reader.pdf_path", return_value=self.path),
                        patch("knowledge.course.get_section", return_value={"id": 1})]
        for item in self.patches: item.start()

    def tearDown(self):
        for item in reversed(self.patches): item.stop()
        self.temp.cleanup()

    def test_preserves_cross_page_geometry_and_only_transfers_source_pointers(self):
        result = {"reply": "核验后的回答", "pdf_references": [{"evidence": {
            "document_id": "published-chapter", "document_version": self.version,
            "evidence_id": "evidence-1", "section_id": 1, "quote": "教材原文"}}]}
        row = {"student_id": "s", "session_id": "tab", "id": "task", "revision": 3,
               "status": "completed", "payload": self.payload, "result": result,
               "context": {"document_versions": {"published-chapter": self.version}}}
        projection = projection_for(row)
        self.assertEqual([r.model_dump() for r in projection.sources[0].rects], self.rects)
        self.assertEqual([source.kind for source in projection.sources], ["selection", "section", "citation"])
        transferred = projection.model_dump_json()
        for text in ("学生的问题", "浏览器预览文字", "核验后的回答", "教材原文"):
            self.assertNotIn(text, transferred)
        self.assertEqual(projection.sources[-1].evidence_id, "evidence-1")

    def test_source_manifest_or_file_change_is_rejected(self):
        with self.assertRaises(ValueError):
            source_pointers({"selection": {**self.payload["selection"], "version": "0" * 64}}, {})
        self.path.write_bytes(b"changed textbook")
        with self.assertRaises(ValueError): source_pointers(self.payload, {})

    def test_location_without_historical_version_cannot_claim_current_revision(self):
        with self.assertRaises(ValueError):
            source_pointers({"reader_location": {"chapter_id": 1, "section_id": 1}}, {})
        with self.assertRaises(ValueError):
            source_pointers({}, {}, {"published-chapter": "0" * 64})

    def test_digest_keeps_symbols_and_matches_full_saved_result(self):
        row = {"student_id": "s", "session_id": "tab", "id": "task", "revision": 3,
               "status": "completed", "payload": {}, "result": {"reply": "x-1"}}
        first = projection_for(row)
        row["result"] = {"reply": "x1"}
        second = projection_for(row)
        self.assertNotEqual(first.result_digest, second.result_digest)
        self.assertEqual(second.result_digest, hashlib.sha256(json.dumps(row["result"], ensure_ascii=False, sort_keys=True).encode()).hexdigest())

    def test_unordered_and_nonfinite_geometry_is_rejected(self):
        for values in ({"x1": .9, "x2": .2}, {"y1": .4, "y2": .3}, {"x1": float("nan")}):
            with self.assertRaises(ValueError): SourceRect(**{**self.rects[0], **values})


if __name__ == "__main__":
    unittest.main()
