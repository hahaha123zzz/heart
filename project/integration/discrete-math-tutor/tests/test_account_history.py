"""在临时 SQLite 库上验证正式账号归属与历史问题图，不接真实 LLM。"""

import datetime as dt
import asyncio
import os
import sys
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

_temp = tempfile.TemporaryDirectory(prefix="dm-auth-test-")
os.environ["DATABASE_URL"] = "sqlite:///" + _temp.name.replace("\\", "/") + "/test.db"
os.environ["LLM_MOCK"] = "1"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
from database.database import engine, session_scope  # noqa: E402
from database.models import (AuthSessionRow, ConversationRow, QuestionAnalysisJobRow,
                             Student, UserRow)  # noqa: E402
import history_map  # noqa: E402
from main import app  # noqa: E402


class AccountHistoryTests(unittest.TestCase):
    def test_accounts_and_map(self):
        first = TestClient(app)
        other_browser = TestClient(app)
        second = TestClient(app)
        self.assertEqual(first.get("/api/students/unknown/dashboard").status_code, 401)
        for private_path in ("/api/students/unknown/profile", "/api/students/unknown/evidence",
                             "/api/students/unknown/conversation", "/api/students/unknown/history-map",
                             "/api/practice/chapters/1"):
            self.assertEqual(first.get(private_path).status_code, 401, private_path)
        self.assertEqual(first.post("/api/course/views", json={"chapter_id":1,"section_id":1}).status_code, 401)

        user = first.post("/api/auth/register", json={"username":"student_one","password":"secret-password-1"})
        self.assertEqual(user.status_code, 200, user.text)
        sid = user.json()["student_id"]
        csrf = user.json()["csrf_token"]
        self.assertIn("httponly", user.headers["set-cookie"].lower())
        with session_scope() as db:
            stored = db.scalar(select(UserRow).where(UserRow.student_id == sid))
            self.assertTrue(stored.password_hash.startswith("$argon2"))
            self.assertNotEqual(stored.password_hash, "secret-password-1")
        self.assertEqual(first.put(f"/api/students/{sid}/preferences", json={}).status_code, 403)
        saved = first.put(f"/api/students/{sid}/preferences", json={"answer_length":1},
                          headers={"X-CSRF-Token":csrf})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(first.put(f"/api/students/{sid}/preferences", json={"answer_length":0},
                                   headers={"X-CSRF-Token":csrf, "Origin":"https://other.example"}).status_code, 403)
        self.assertEqual(first.post("/api/auth/login", json={"username":"student_one","password":"secret-password-1"},
                                    headers={"Origin":"https://other.example"}).status_code, 403)

        login = other_browser.post("/api/auth/login", json={"username":"student_one","password":"secret-password-1"})
        self.assertEqual(login.status_code, 200, login.text)
        self.assertEqual(login.json()["student_id"], sid)
        self.assertEqual(other_browser.get(f"/api/students/{sid}/preferences").json()["answer_length"], 1)

        user2 = second.post("/api/auth/register", json={"username":"student_two","password":"secret-password-2"})
        self.assertEqual(user2.status_code, 200, user2.text)
        sid2 = user2.json()["student_id"]
        csrf2 = user2.json()["csrf_token"]
        self.assertNotEqual(sid, sid2)
        self.assertEqual(second.get(f"/api/students/{sid}/conversation").status_code, 404)
        self.assertEqual(second.get(f"/api/practice/chapters/1?student_id={sid}").status_code, 404)
        self.assertEqual(second.put("/api/practice/questions/not-a-question/draft",
                                    json={"student_id":sid,"version":"x"*64},
                                    headers={"X-CSRF-Token":csrf2}).status_code, 404)

        # 独立构造已保存的问答；只测试历史索引，不改变 Agent 教学策略。
        decisions = [
            {"action":"new_root","title":"空集为何是子集"},
            {"action":"child","title":"什么是空真命题","parent_id":1},
            {"action":"child","title":"假前件蕴含为何真","parent_id":2},
            {"action":"child","title":"子集与属于的区别","parent_id":1},
            {"action":"continue","parent_id":1},
            {"action":"ignore"},
        ]
        with patch.object(history_map, "_classify", side_effect=decisions):
            for message in ["为什么空集是任何集合的子集？", "什么是空真命题？",
                            "为什么前件为假时蕴含命题为真？", "子集和属于有什么区别？",
                            "那空集这个问题再解释一下？", "谢谢"]:
                turn = str(uuid.uuid4())
                with session_scope() as db:
                    db.add(ConversationRow(student_id=sid, turn_id=turn, role="user", content=message))
                    db.add(ConversationRow(student_id=sid, turn_id=turn, role="assistant", content="原始助教回答"))
                    db.add(QuestionAnalysisJobRow(turn_id=turn, student_id=sid))
                history_map.process_job(turn)

        tree = first.get(f"/api/students/{sid}/history-map")
        self.assertEqual(tree.status_code, 200, tree.text)
        nodes = tree.json()["nodes"]
        self.assertEqual(len(nodes), 4)
        self.assertEqual([node["parent_id"] for node in nodes], [None, 1, 2, 1])
        messages = first.get(f"/api/students/{sid}/history-map/1/messages").json()["messages"]
        self.assertEqual(len(messages), 4)
        self.assertTrue(all(isinstance(m["id"], int) for m in messages))
        self.assertEqual(second.get(f"/api/students/{sid}/history-map").status_code, 404)
        self.assertEqual(second.get(f"/api/students/{sid2}/history-map/1/messages").status_code, 404)

        # 真正经过聊天 SSE 入口，身份由 Cookie 决定，正常回答不等待历史图 LLM。
        streamed = second.post("/api/chat/stream", json={"message":"为什么空集是子集？"},
                               headers={"X-CSRF-Token":csrf2})
        self.assertEqual(streamed.status_code, 200, streamed.text[:500])
        self.assertIn("event: done", streamed.text)
        own_chat = second.get(f"/api/students/{sid2}/conversation").json()
        self.assertTrue(any(row["role"] == "user" for row in own_chat))
        self.assertEqual(first.get(f"/api/students/{sid}/history-map").json()["nodes"], nodes)

        self.assertEqual(first.post("/api/auth/logout", headers={"X-CSRF-Token":csrf}).status_code, 200)
        self.assertEqual(first.get("/api/auth/me").status_code, 401)
        self.assertEqual(other_browser.get(f"/api/students/{sid}/history-map").json()["nodes"], nodes)

        with session_scope() as db:
            session = db.scalar(select(AuthSessionRow).where(AuthSessionRow.user_id == user2.json().get("user_id", -1)))
            if session is None:
                session = db.scalar(select(AuthSessionRow).join(UserRow).where(UserRow.student_id == sid2))
            session.expires_at = dt.datetime.utcnow() - dt.timedelta(seconds=1)
            db.add(Student(student_id="legacy-test-data", account_type="test",
                           expires_at=dt.datetime.utcnow() - dt.timedelta(days=30)))
        self.assertEqual(second.get("/api/auth/me").status_code, 401)
        from orchestrator import TutorOrchestrator
        TutorOrchestrator()
        with session_scope() as db:
            self.assertIsNotNone(db.get(Student, sid2))
            self.assertIsNotNone(db.get(Student, "legacy-test-data"))


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        engine.dispose()
        _temp.cleanup()
