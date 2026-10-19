"""宿主边界测试可在原环境运行；上游存储测试在独立环境运行。"""
import asyncio
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from integrations.deeptutor.boundary import HostBridgeBoundary
from integrations.deeptutor.client import BackendUnavailable, DeepTutorBackend
from integrations.deeptutor.session_bridge import SessionBindingRequest, SessionBridge, install_session_bridge
from integrations.deeptutor.session_sync import sync_completed_session

TOKEN = "integration-test-token-000000000000000000"


class SessionBoundaryTests(unittest.TestCase):
    def test_client_owns_course_and_drops_internal_fields(self):
        client = DeepTutorBackend()
        payload = dict(user_id="u", course_id="c", session_id="s", role="student", private="secret")
        with patch.dict(os.environ, DEEPTUTOR_BRIDGE_TOKEN=TOKEN), patch.object(client.opener, "open", return_value=io.BytesIO(json.dumps(payload).encode())) as opened:
            result = client.bind_session("student", "tab")
        request = opened.call_args.args[0]
        data = json.loads(request.data)
        from knowledge.course_config import COURSE_ID
        self.assertEqual(data["course_id"], COURSE_ID)
        self.assertEqual(data["student_id"], "student")
        self.assertEqual(request.get_header("X-heart-bridge-token"), TOKEN)
        self.assertNotIn("private", result)

    def test_no_token_never_sends(self):
        client = DeepTutorBackend()
        with patch.dict(os.environ, DEEPTUTOR_BRIDGE_TOKEN=""), patch.object(client.opener, "open") as opened:
            with self.assertRaises(BackendUnavailable): client.bind_session("s", "tab")
        opened.assert_not_called()

    def test_client_rejects_admin_identity(self):
        client = DeepTutorBackend()
        with patch.dict(os.environ, DEEPTUTOR_BRIDGE_TOKEN=TOKEN), patch.object(client.opener, "open", return_value=io.BytesIO(b'{"user_id":"u","course_id":"c","session_id":"s","role":"admin"}')):
            with self.assertRaises(BackendUnavailable): client.bind_session("s", "tab")

    def test_http_and_websocket_are_closed_without_token(self):
        from starlette.websockets import WebSocketDisconnect
        app = FastAPI()
        @app.get("/health/ready")
        def ready(): return {"status": "ready"}
        @app.get("/api/sessions")
        def sessions(): return {"private": True}
        app.add_middleware(HostBridgeBoundary)
        with patch.dict(os.environ, DEEPTUTOR_BRIDGE_TOKEN=TOKEN), TestClient(app) as client:
            self.assertEqual(client.get("/health/ready").status_code, 200)
            self.assertEqual(client.get("/api/sessions").status_code, 401)
            self.assertEqual(client.get("/api/sessions", headers={"X-Heart-Bridge-Token": TOKEN}).status_code, 200)
            with self.assertRaises(WebSocketDisconnect):
                with client.websocket_connect("/ws/chat"): pass

    def test_binding_endpoint_auth_and_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            app = FastAPI()
            install_session_bridge(app, Path(temp))
            client = TestClient(app)
            payload = dict(student_id="s", course_id="course", course_title="教材", session_id="tab")
            with patch.dict(os.environ, DEEPTUTOR_BRIDGE_TOKEN=TOKEN):
                self.assertEqual(client.post("/internal/heart/session", json=payload).status_code, 401)
                response = client.post("/internal/heart/session", json={**payload, "role": "admin"}, headers={"X-Heart-Bridge-Token": TOKEN})
                self.assertEqual(response.status_code, 422)
            with patch.dict(os.environ, DEEPTUTOR_BRIDGE_TOKEN=""):
                self.assertEqual(client.post("/internal/heart/session", json=payload).status_code, 503)
            client.close()

    def test_sync_only_after_verified_save_and_failure_is_explicit(self):
        request = SimpleNamespace(student_id="s", session_id="tab")
        with patch.dict(os.environ, DEEPTUTOR_SESSION_SYNC="1"), patch.object(DeepTutorBackend, "bind_session", side_effect=BackendUnavailable("private")) as bind:
            for result in ({"answer_status": "task_busy"}, {"answer_status": "answered"}):
                self.assertIs(sync_completed_session(request, result), result)
            bind.assert_not_called()
            saved = {"answer_status": "answered", "conversation_id": 1, "reply": "已核验", "step_advanced": False}
            result = sync_completed_session(request, saved)
            self.assertEqual(result["reply"], "已核验")
            self.assertEqual(result["deeptutor_session"], {"status": "unavailable"})
            self.assertNotIn("private", str(result))


class UpstreamSessionTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.util
        if importlib.util.find_spec("deeptutor") is None:
            raise unittest.SkipTest("上游存储测试需要 .venv-deeptutor")

    async def test_retry_recovers_partial_upstream_write(self):
        from deeptutor.services.session import SQLiteSessionStore
        with tempfile.TemporaryDirectory() as temp:
            bridge = SessionBridge(Path(temp))
            request = SessionBindingRequest(student_id="partial-write", course_id="course", course_title="教材", session_id="tab")
            with patch.object(SQLiteSessionStore, "update_session_preferences", side_effect=RuntimeError("injected write failure")):
                with self.assertRaises(RuntimeError):
                    await bridge.bind(request)
            result = await bridge.bind(request)
            self.assertEqual(result, await SessionBridge(Path(temp)).bind(request))
            with bridge._connect() as db:
                for table in ("users", "courses", "sessions"):
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0], 1)
            courses = list((bridge.root / "users").rglob("courses.json"))
            self.assertEqual(len(courses), 1)
            self.assertEqual(len(json.loads(courses[0].read_text(encoding="utf-8"))["courses"]), 1)

    async def test_durable_isolation_idempotency_and_course_membership(self):
        from deeptutor.multi_user.context import get_current_user_or_none
        from deeptutor.multi_user.models import CurrentUser, UserScope
        from deeptutor.multi_user.paths import user_context
        from deeptutor.services.courses import CourseService
        from deeptutor.services.session import get_sqlite_session_store
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            bridge = SessionBridge(home)
            request = SessionBindingRequest(student_id="../../学生甲", course_id="psychology", course_title="实验心理学", session_id="tab-a")
            first, duplicate = await asyncio.gather(bridge.bind(request), bridge.bind(request))
            self.assertEqual(first, duplicate)
            self.assertEqual(first, await SessionBridge(home).bind(request))
            tab = await bridge.bind(request.model_copy(update={"session_id": "tab-b"}))
            student = await bridge.bind(request.model_copy(update={"student_id": "学生乙"}))
            other_course = await bridge.bind(request.model_copy(update={"course_id": "other"}))
            self.assertEqual(first["user_id"], tab["user_id"])
            self.assertNotEqual(first["session_id"], tab["session_id"])
            self.assertNotEqual(first["user_id"], student["user_id"])
            self.assertNotEqual(first["course_id"], other_course["course_id"])
            for binding in (first, student):
                root = bridge.root / "users" / binding["user_id"]
                self.assertTrue(root.resolve().is_relative_to(bridge.root.resolve()))
                user = CurrentUser(binding["user_id"], "student", "student", UserScope("user", binding["user_id"], root))
                with user_context(user):
                    self.assertFalse(user.is_admin)
                    store = get_sqlite_session_store()
                    session = await store.get_session(binding["session_id"])
                    self.assertEqual(session["preferences"]["course_id"], binding["course_id"])
                    self.assertTrue(session["preferences"]["heart_managed"])
                    self.assertEqual(await store.get_messages(binding["session_id"]), [])
                    self.assertEqual(CourseService().get(binding["course_id"]).default_capability, "chat")
                    other = student if binding is first else first
                    self.assertIsNone(await store.get_session(other["session_id"]))
            self.assertIsNone(get_current_user_or_none())


if __name__ == "__main__":
    unittest.main()
