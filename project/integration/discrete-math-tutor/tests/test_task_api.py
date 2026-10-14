"""HTTP/SSE接线验证；替换应用启动依赖，不连接真实数据库。"""
import importlib
import sys
import unittest
from unittest.mock import Mock, patch
import tempfile
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from database import database as db
from database.models import Base
from memory.memory_manager import MemoryManager
from database.learning_tasks import LearningTaskRepository
from models.task_understanding import TaskUnderstanding
from fastapi.testclient import TestClient


class TaskAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous = sys.modules.pop("main", None)
        cls.temp = tempfile.TemporaryDirectory()
        cls.engine = create_engine("sqlite:///" + cls.temp.name.replace("\\", "/") + "/api.db", connect_args={"check_same_thread": False})
        @event.listens_for(cls.engine, "connect")
        def fk(connection, _): connection.execute("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(cls.engine)
        cls.db_patch = patch.object(db, "SessionLocal", sessionmaker(bind=cls.engine, autoflush=False, expire_on_commit=False))
        cls.db_patch.start()
        cls.tutor = Mock()
        cls.tutor.memory = MemoryManager()
        cls.tutor.handle_turn.return_value = {"reply": "测试回复"}
        with patch("orchestrator.TutorOrchestrator", return_value=cls.tutor), patch("database.database.init_db"), patch("practice_api.recover_interrupted_submissions"):
            cls.module = importlib.import_module("main")
        cls.client = TestClient(cls.module.app)  # 不触发真实lifespan工作线程。

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls.db_patch.stop(); cls.engine.dispose(); cls.temp.cleanup()
        sys.modules.pop("main", None)
        if cls.previous is not None:
            sys.modules["main"] = cls.previous

    def setUp(self):
        self.tutor.handle_turn.reset_mock()
        self.tutor.handle_turn.side_effect = None

    def test_old_request_remains_compatible(self):
        response = self.client.post("/api/chat", json={"message": "解释图"})
        self.assertEqual(response.status_code, 200)
        context = self.tutor.handle_turn.call_args.kwargs["task_context"]
        self.assertEqual(context.session_id, "legacy")
        self.assertEqual(context.objects, [])

    def test_both_endpoints_reject_invalid_reader_before_work(self):
        for endpoint in ("/api/chat", "/api/chat/stream"):
            response = self.client.post(endpoint, json={"message": "解释", "reader_location": {"chapter_id": 7, "section_id": 99999}})
            self.assertEqual(response.status_code, 422)
        self.tutor.handle_turn.assert_not_called()

    def test_sse_carries_resolved_location(self):
        self.tutor.memory.ensure_student("s", account_type="test")
        self.tutor.memory.repo.set_explicit_preferences("s", {"answer_length": .5})
        response = self.client.post("/api/chat/stream", json={"student_id": "s", "message": "解释本小节", "session_id": "tab-a",
            "reader_location": {"chapter_id": 7, "section_id": 1}})
        self.assertEqual(response.status_code, 200)
        self.assertIn("event: done", response.text)
        self.assertIn("测试回复", response.text)
        context = self.tutor.handle_turn.call_args.kwargs["task_context"]
        self.assertEqual(context.objects[0].id, "section:7:1")
        self.assertEqual(context.student_id, "s")
        self.assertEqual(context.session_id, "tab-a")
        self.assertEqual(context.preferences["answer_length"], .5)

    def test_pdf_version_is_checked_before_selection_handler(self):
        selection = {"document_id": "chapter-07", "version": "0" * 64, "kind": "area",
            "rects": [{"page": 1, "x1": .1, "y1": .1, "x2": .2, "y2": .2}]}
        with patch("agents.pdf_selection_tutor.explain_selection") as explain:
            for endpoint in ("/api/chat", "/api/chat/stream"):
                self.assertEqual(self.client.post(endpoint, json={"message": "解释", "selection": selection}).status_code, 422)
        explain.assert_not_called()

    def test_pending_restore_and_cancel_endpoints(self):
        def clarify(*args, **kwargs):
            return kwargs["routing_interceptor"](TaskUnderstanding(status="unknown", intent="clarify_task", missing_slots=["target"]), kwargs["task_context"])
        self.tutor.handle_turn.side_effect = clarify
        payload = {"student_id": "pending-api", "message": "这个怎么证明", "session_id": "tab", "request_id": "r1"}
        first = self.client.post("/api/chat", json=payload).json()
        self.assertEqual(first["answer_status"], "awaiting_clarification")
        restored = self.client.get("/api/chat/tasks/pending", params={"student_id": "pending-api", "session_id": "tab"}).json()
        self.assertEqual(restored["pending"], first)
        other = self.client.get("/api/chat/tasks/pending", params={"student_id": "pending-api", "session_id": "other"}).json()
        self.assertIsNone(other["pending"])
        cancelled = self.client.request("DELETE", "/api/chat/tasks/" + first["task_id"], json={"student_id": "pending-api", "session_id": "tab", "task_revision": first["task_revision"]}).json()
        self.assertEqual(cancelled["answer_status"], "task_cancelled")

    def test_sse_clarification_stops_before_teaching(self):
        def clarify(*args, **kwargs):
            return kwargs["routing_interceptor"](TaskUnderstanding(status="unknown", intent="clarify_task", missing_slots=["topic"]), kwargs["task_context"])
        self.tutor.handle_turn.side_effect = clarify
        response = self.client.post("/api/chat/stream", json={"student_id": "stream-pending", "message": "这个", "session_id": "tab"})
        self.assertIn('"answer_status": "awaiting_clarification"', response.text)
        self.assertIn('"task_revision":', response.text)
        self.assertIn("event: done", response.text)

    def test_rollout_off_restores_no_pending_and_sse_blocks_old_reply(self):
        def clarify(*args, **kwargs):
            return kwargs['routing_interceptor'](TaskUnderstanding(intent='clarify_task', missing_slots=['target']), kwargs['task_context'])
        self.tutor.handle_turn.side_effect=clarify
        first=self.client.post('/api/chat',json={'student_id':'rollback-api','message':'这个','session_id':'tab','request_id':'rb1'}).json()
        with patch.dict('os.environ', {'INTENT_ROLLOUT':'off'}):
            restored=self.client.get('/api/chat/tasks/pending',params={'student_id':'rollback-api','session_id':'tab'}).json()
            self.assertIsNone(restored['pending'])
            self.assertIn('失效',restored['notice'])
            self.tutor.handle_turn.reset_mock()
            response=self.client.post('/api/chat/stream',json={'student_id':'rollback-api','message':'第一个','session_id':'tab',
                'request_id':'rb2','task_id':first['task_id'],'task_revision':first['task_revision']})
            self.assertIn('"answer_status": "task_disabled"',response.text)
            self.tutor.handle_turn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
