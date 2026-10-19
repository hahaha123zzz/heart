"""真实上游 Markdown 知识库发布、搜索、版本校验与课程绑定。"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

from integrations.deeptutor.published_course import COURSE, publish, read_pack
from integrations.deeptutor.knowledge_bridge import KnowledgeQuery, search
from integrations.deeptutor.knowledge_client import supplement
from integrations.deeptutor.client import DeepTutorBackend
from llm.client import LLMError


class CanonicalRetrievalTests(unittest.TestCase):
    def test_rejects_wrong_course_and_unknown_index(self):
        for result in ({"course_id":"other", "chunk_ids":[]}, {"course_id":COURSE,"chunk_ids":["unknown"],"index_sha256":"0"*64}):
            with patch.object(DeepTutorBackend, "_post", return_value=result):
                with self.assertRaises(LLMError): supplement("随机分配", [])


class PublishedKnowledgeTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        if importlib.util.find_spec("deeptutor") is None: raise unittest.SkipTest("知识库发布测试需要独立环境")

    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / "runtime"
        self.source = Path(self.temp.name) / "source"
        (self.source / "source").mkdir(parents=True)
        (self.source / "source/textbook.docx").write_bytes(b"book fixture")
        pdf = self.source / "chapters/chapter_01/chapter_01.generated.pdf"
        pdf.parent.mkdir(parents=True); pdf.write_bytes(b"pdf fixture")
        self.documents = [{"document_id":"published-chapter-1", "chapter_id":1,"version":hashlib.sha256(pdf.read_bytes()).hexdigest()}]
        (self.source / "pdf_manifest.json").write_text(json.dumps(self.documents), encoding="utf-8")
        (self.source / "manifest.json").write_text(json.dumps({"course_id":COURSE,"title":"实验心理学", "source_sha256":{
            "textbook.docx":hashlib.sha256(b"book fixture").hexdigest()}}), encoding="utf-8")
        with closing(sqlite3.connect(self.source / "rag_index.sqlite3")) as db:
            db.execute("CREATE TABLE chunks(id TEXT,chapter_id INTEGER,section_id INTEGER,page INTEGER,block_start INTEGER,block_end INTEGER,kind TEXT,source TEXT,section TEXT,text TEXT)")
            db.execute("INSERT INTO chunks VALUES(?,1,1,2,3,3,'text','教材','随机分配',?)", ("course:ch1:block3", "随机分配可以帮助控制无关变量。x-1 与 x1 不同。"))
            db.commit()

    async def asyncTearDown(self):
        self.temp.cleanup()

    async def test_publish_search_and_repeat_preserve_original_identity(self):
        first = publish(self.home, self.source)
        self.assertEqual(first, publish(self.home, self.source))
        directory, manifest = read_pack(self.home)
        self.assertFalse(first["vector_indexed"])
        self.assertEqual(manifest["documents"], {"published-chapter-1":self.documents[0]["version"]})
        result = search(self.home, KnowledgeQuery(terms=["随机分配"]))
        self.assertEqual(result["chunk_ids"], ["course:ch1:block3"])
        note = next((directory / "vault").rglob("*.md")).read_text(encoding="utf-8")
        self.assertIn("x-1 与 x1 不同", note)

    async def test_tampering_blocks_search_and_does_not_republish(self):
        publish(self.home, self.source)
        directory, _ = read_pack(self.home)
        note = next((directory / "vault").rglob("*.md"))
        note.write_text("tampered", encoding="utf-8")
        with self.assertRaises(ValueError): search(self.home, KnowledgeQuery(terms=["tampered"]))
        with self.assertRaises(ValueError): publish(self.home, self.source)

    async def test_changed_source_produces_new_immutable_version(self):
        first = publish(self.home, self.source)
        with closing(sqlite3.connect(self.source / "rag_index.sqlite3")) as db:
            db.execute("UPDATE chunks SET text='更新后的随机分配教材' WHERE id='course:ch1:block3'")
            db.commit()
        second = publish(self.home, self.source)
        self.assertNotEqual(first["version"], second["version"])
        self.assertTrue((self.home / "published" / COURSE / first["version"]).is_dir())
        self.assertEqual(read_pack(self.home)[1]["version"], second["version"])

    async def test_bad_pdf_is_rejected_before_publishing(self):
        (self.source / "chapters/chapter_01/chapter_01.generated.pdf").write_bytes(b"changed")
        with self.assertRaises(ValueError): publish(self.home, self.source)
        self.assertFalse((self.home / "published" / COURSE / "current.json").exists())

    async def test_native_knowledge_manager_and_course_resource_are_bound(self):
        from integrations.deeptutor.session_bridge import SessionBindingRequest, SessionBridge
        from integrations.deeptutor.turn_bridge import scoped_store
        from deeptutor.knowledge.manager import KnowledgeBaseManager
        from deeptutor.services.path_service import get_path_service
        from deeptutor.services.courses import CourseService
        publish(self.home, self.source)
        sessions = SessionBridge(self.home)
        binding = await sessions.bind(SessionBindingRequest(student_id="s", course_id=COURSE,course_title="实验心理学",session_id="tab"))
        with scoped_store(sessions, binding["user_id"]):
            course = CourseService().get(binding["course_id"])
            resources = [item for item in course.resources if item.kind == "knowledge_base"]
            self.assertEqual(len(resources), 1)
            manager = KnowledgeBaseManager(get_path_service().get_knowledge_bases_root())
            self.assertEqual(manager.config["knowledge_bases"][resources[0].ref_id]["type"], "obsidian")
