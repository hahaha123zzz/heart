"""HTTP/SSE接线验证；替换应用启动依赖，不连接真实数据库。"""
import importlib
import os
import json
from contextlib import contextmanager
from uuid import uuid4
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

    def _recovery_turn(self, *, clarification=False):
        def answer(*args, **kwargs):
            routing = TaskUnderstanding(status="unknown", intent="clarify_task", missing_slots=["topic"]) if clarification else TaskUnderstanding()
            halted = kwargs["routing_interceptor"](routing, kwargs["task_context"])
            if halted is not None: return halted
            cid = self.tutor.memory.append_exchange(args[0], args[1], "核验后的回答", task_guard=kwargs["task_guard"])
            return {"answer_status": "answered", "reply": "核验后的回答", "conversation_id": cid, "step_advanced": False}
        self.tutor.handle_turn.side_effect = answer
        payload = {"student_id": "recover-" + uuid4().hex, "session_id": "tab", "request_id": "request", "message": "学生问题正文"}
        with patch.dict(os.environ, DEEPTUTOR_TURN_SYNC="0"):
            result = self.client.post("/api/chat", json=payload).json()
        return payload, result

    @contextmanager
    def _turn_transport(self):
        from integrations.deeptutor.client import DeepTutorBackend
        saved = {}
        def post(path, payload):
            if path == "/internal/heart/turn":
                saved.update(payload)
                return {"turn_id": "test-turn", "last_seq": 2, "task_id": payload["task_id"], "task_revision": payload["task_revision"]}
            metadata = {"host_task_id": saved["task_id"], "host_task_revision": saved["task_revision"],
                        "outcome": saved["outcome"], "result_digest": saved["result_digest"]}
            events = [{"seq": 1, "type": "sources", "content": "", "metadata": {"sources": saved["sources"]}},
                      {"seq": 2, "type": "done", "content": "", "metadata": metadata}]
            return {"events": [event for event in events if event["seq"] > payload["after_seq"]], "last_seq": 2}
        with patch.dict(os.environ, DEEPTUTOR_TURN_SYNC="1"), patch.object(DeepTutorBackend, "_post", side_effect=post) as transport:
            yield saved, transport

    def test_request_lookup_recovers_saved_answer_and_checks_owner(self):
        payload, saved = self._recovery_turn()
        params = {key: payload[key] for key in ("student_id", "session_id")}
        restored = self.client.get("/api/chat/requests/request", params=params)
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.headers["cache-control"], "no-store")
        self.assertEqual(restored.json()["result"], saved)
        self.assertEqual(self.client.get("/api/chat/requests/request", params={**params, "session_id": "other"}).status_code, 404)
        self.assertEqual(self.client.get("/api/chat/requests/request", params={**params, "student_id": "other"}).status_code, 404)
        self.tutor.handle_turn.assert_called_once()

    def test_durable_events_hydrate_receipt_and_support_cursor(self):
        payload, saved = self._recovery_turn()
        params = {key: payload[key] for key in ("student_id", "session_id")}
        params["task_revision"] = saved["task_revision"]
        url = "/api/chat/tasks/" + saved["task_id"] + "/events"
        with self._turn_transport() as (projection, _):
            replay = self.client.get(url, params=params)
            self.assertEqual(replay.status_code, 200)
            self.assertIn("event: sources", replay.text)
            self.assertIn("核验后的回答", replay.text)
            self.assertIn(f"id: {saved['task_id']}:{saved['task_revision']}:2", replay.text)
            next_events = self.client.get(url, params=params, headers={"Last-Event-ID": f"{saved['task_id']}:{saved['task_revision']}:1"})
            self.assertNotIn("event: sources", next_events.text)
            self.assertIn("event: done", next_events.text)
            self.assertEqual(self.client.get(url, params={**params, "after_seq": 2}).text, "")
            self.assertEqual(self.client.get(url, params=params, headers={"Last-Event-ID": "other:3:1"}).status_code, 422)
        self.assertNotIn("学生问题正文", json.dumps(projection, ensure_ascii=False))
        self.assertNotIn("核验后的回答", json.dumps(projection, ensure_ascii=False))
        self.tutor.handle_turn.assert_called_once()
        self.assertEqual(len(self.tutor.memory.repo.get_conversation_with_figures(payload["student_id"])), 2)

    def test_deleted_memory_is_not_restored_from_upstream_events(self):
        payload, saved = self._recovery_turn()
        row = LearningTaskRepository().get(payload["student_id"], "tab", saved["task_id"])
        self.tutor.memory.forget_point(payload["student_id"], row["knowledge_point"])
        with self._turn_transport() as (_, transport):
            params = {"student_id": payload["student_id"], "session_id": "tab", "task_revision": saved["task_revision"]}
            response = self.client.get("/api/chat/tasks/" + saved["task_id"] + "/events", params=params)
            self.assertIn(response.status_code, (404, 410))
            self.assertNotIn("核验后的回答", response.text)
            transport.assert_not_called()

    def test_cancelled_clarification_cannot_replay_old_version(self):
        payload, saved = self._recovery_turn(clarification=True)
        cancelled = self.client.request("DELETE", "/api/chat/tasks/" + saved["task_id"], json={
            "student_id": payload["student_id"], "session_id": "tab", "task_revision": saved["task_revision"]}).json()
        with self._turn_transport() as (_, transport):
            params = {"student_id": payload["student_id"], "session_id": "tab", "task_revision": saved["task_revision"]}
            url = "/api/chat/tasks/" + saved["task_id"] + "/events"
            self.assertEqual(self.client.get(url, params=params).status_code, 409)
            self.assertEqual(self.client.get(url, params={**params, "task_revision": cancelled["task_revision"]}).status_code, 410)
            transport.assert_not_called()

    def test_delete_during_upstream_wait_is_checked_again(self):
        from integrations.deeptutor.client import DeepTutorBackend
        payload, saved = self._recovery_turn()
        row = LearningTaskRepository().get(payload["student_id"], "tab", saved["task_id"])
        def during_wait(cursor):
            self.tutor.memory.forget_point(payload["student_id"], row["knowledge_point"])
            return {"events": []}
        with self._turn_transport(), patch.object(DeepTutorBackend, "turn_events", side_effect=during_wait):
            response = self.client.get("/api/chat/tasks/" + saved["task_id"] + "/events", params={
                "student_id": payload["student_id"], "session_id": "tab", "task_revision": saved["task_revision"]})
        self.assertIn(response.status_code, (404, 410))
        self.assertNotIn("核验后的回答", response.text)

    def test_repeated_request_syncs_saved_turn_without_regeneration(self):
        payload, saved = self._recovery_turn()
        with self._turn_transport() as (projection, _):
            response = self.client.post("/api/chat/stream", json=payload)
        self.assertIn('"deeptutor_turn": {"status": "ready"', response.text)
        self.assertEqual(projection["task_id"], saved["task_id"])
        self.assertEqual(projection["task_revision"], saved["task_revision"])
        self.tutor.handle_turn.assert_called_once()

    def test_published_textbook_change_blocks_restore_before_upstream_access(self):
        from knowledge.pdf_reader import documents
        payload, saved = self._recovery_turn()
        changed = [{**record, "version": "0" * 64} for record in documents()]
        with self._turn_transport() as (_, transport), patch("knowledge.pdf_reader.documents", return_value=changed):
            params = {"student_id": payload["student_id"], "session_id": "tab", "task_revision": saved["task_revision"]}
            response = self.client.get("/api/chat/tasks/" + saved["task_id"] + "/events", params=params)
            self.assertEqual(response.status_code, 410)
            self.assertEqual(response.json()["detail"]["code"], "source_changed")
            self.assertEqual(self.client.get("/api/chat/requests/request", params=params).status_code, 410)
            transport.assert_not_called()

    def test_expired_task_cannot_recover_saved_body(self):
        import datetime as dt
        from database.database import session_scope
        from database.learning_tasks import now
        from database.models import LearningTaskRow
        payload, saved = self._recovery_turn()
        with session_scope() as db:
            db.get(LearningTaskRow, saved["task_id"]).expires_at = now() - dt.timedelta(seconds=1)
        response = self.client.get("/api/chat/requests/request", params={"student_id": payload["student_id"], "session_id": "tab"})
        self.assertEqual(response.status_code, 410)
        self.assertNotIn("核验后的回答", response.text)

    def test_old_request_remains_compatible(self):
        response = self.client.post("/api/chat", json={"message": "解释图"})
        self.assertEqual(response.status_code, 200)
        context = self.tutor.handle_turn.call_args.kwargs["task_context"]
        self.assertEqual(context.session_id, "legacy")
        self.assertEqual(context.objects, [])

    def test_deeptutor_session_requires_existing_student_and_server_owns_identity(self):
        from integrations.deeptutor.client import DeepTutorBackend
        self.tutor.memory.ensure_student("bridge-student", account_type="test")
        binding = dict(user_id="upstream-user", course_id="upstream-course", session_id="upstream-session", role="student")
        with patch.object(DeepTutorBackend, "bind_session", return_value=binding) as bind:
            response = self.client.post("/api/deeptutor/session", json={"student_id": "bridge-student", "session_id": "tab"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), binding)
            bind.assert_called_once_with("bridge-student", "tab")
            bind.reset_mock()
            self.assertEqual(self.client.post("/api/deeptutor/session", json={"student_id": "missing-student"}).status_code, 404)
            for injected in ({"course_id": "another-course"}, {"role": "admin"}, {"user_id": "another-user"}):
                self.assertEqual(self.client.post("/api/deeptutor/session", json={"student_id": "bridge-student", **injected}).status_code, 422)
            bind.assert_not_called()

    def test_completed_chat_retries_binding_without_repeating_saved_turn(self):
        from integrations.deeptutor.client import BackendUnavailable, DeepTutorBackend
        def answer(*args, **kwargs):
            context = kwargs["task_context"]
            kwargs["routing_interceptor"](TaskUnderstanding(), context)
            cid = self.tutor.memory.append_exchange(args[0], args[1], "已核验文字", task_guard=kwargs["task_guard"])
            return {"answer_status": "answered", "reply": "已核验文字", "conversation_id": cid, "step_advanced": False}
        self.tutor.handle_turn.side_effect = answer
        payload = {"student_id": "auto-binding-student", "session_id": "tab", "request_id": "same-request", "message": "解释当前概念"}
        binding = dict(user_id="u", course_id="c", session_id="s", role="student")
        with patch.dict(os.environ, DEEPTUTOR_SESSION_SYNC="1"), patch.object(DeepTutorBackend, "bind_session", side_effect=[BackendUnavailable("unavailable"), binding]) as bind:
            first = self.client.post("/api/chat", json=payload).json()
            second = self.client.post("/api/chat/stream", json=payload)
        self.assertEqual(first["deeptutor_session"], {"status": "unavailable"})
        self.assertIn('"status": "ready"', second.text)
        self.assertIn("event: done", second.text)
        self.assertEqual(bind.call_count, 2)
        self.tutor.handle_turn.assert_called_once()
        self.assertEqual(first["reply"], "已核验文字")
        history = self.tutor.memory.repo.get_conversation_with_figures(payload["student_id"])
        self.assertEqual([item["role"] for item in history], ["user", "assistant"])

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

    def test_sse_publishes_saved_text_before_optional_guide(self):
        order = []
        references=[{'source_index':0,'evidence':{'evidence_id':'stable-source-id','quote':'完整条件',
            'selections':[{'rects':[{'page':19}]},{'rects':[{'page':20}]}]}}]
        def answer(*args, **kwargs):
            context = kwargs["task_context"]
            kwargs["routing_interceptor"](TaskUnderstanding(), context)
            sid = args[0]
            cid = self.tutor.memory.append_exchange(sid, args[1], "核验文字 [1]",
                selection_ref={"section_title": context.knowledge_point,'pdf_references':references}, task_guard=kwargs["task_guard"])
            def guide():
                self.assertEqual(self.tutor.memory.repo.get_conversation_with_figures(sid)[-1]["content"], "核验文字 [1]")
                self.assertEqual(self.tutor.memory.repo.get_conversation_with_figures(sid)[-1]['selection_ref']['pdf_references'],references)
                order.append("build")
                return {"id": "api-guide"}
            kwargs["visualization_jobs"].append(guide)
            return {"answer_status": "answered", "reply": "核验文字 [1]", "conversation_id": cid,'pdf_references':references}
        self.tutor.handle_turn.side_effect = answer
        response = self.client.post("/api/chat/stream", json={"student_id": "progressive-api", "message": "解释定义", "request_id": "progressive-api-r1"})
        import json
        frames = [(next(line[7:] for line in f.split("\n") if line.startswith("event: ")), json.loads(f.split("\ndata: ")[1]))
                  for f in response.text.strip().split("\n\n")]
        events = [name for name, data in frames]
        self.assertLess(events.index("answer"), events.index("done"))
        early = next(data for name, data in frames if name == "answer")
        final = next(data for name, data in frames if name == "done")
        self.assertEqual(early["visualization_status"], "pending")
        self.assertNotIn("guided_visualization", early)
        self.assertEqual(final["guided_visualization"], {"id": "api-guide"})
        self.assertEqual(early["conversation_id"], final["conversation_id"])
        self.assertEqual(early['pdf_references'],references)
        self.assertEqual(final['pdf_references'],references)
        self.assertEqual(order, ["build"])
        rows = self.tutor.memory.repo.get_conversation_with_figures("progressive-api")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[-1]["selection_ref"]["guided_visualization"], final["guided_visualization"])
        self.assertEqual(rows[-1]['selection_ref']['pdf_references'],references)

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
