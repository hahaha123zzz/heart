"""真实上游回合存储的幂等、冲突与中断恢复，不调用模型。"""
import asyncio
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from integrations.deeptutor.session_bridge import SessionBridge
from integrations.deeptutor.turn_bridge import TurnBridge, scoped_store, turn_id
from integrations.deeptutor.turn_contract import TurnCursor, TurnProjection


class UpstreamTurnTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        if importlib.util.find_spec("deeptutor") is None:
            raise unittest.SkipTest("回合存储测试需要 .venv-deeptutor")

    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.sessions = SessionBridge(Path(self.temp.name))
        self.bridge = TurnBridge(self.sessions)
        self.request = TurnProjection(student_id="a", session_id="tab", course_id="psychology",
            course_title="实验心理学", task_id="task", task_revision=3,
            outcome="completed", result_digest="a" * 64)

    async def asyncTearDown(self):
        self.temp.cleanup()

    def cursor(self, **changes):
        return TurnCursor(**{**self.request.model_dump(exclude={"outcome", "result_digest", "sources"}), **changes})

    async def test_idempotent_publish_and_cursor_survive_reconstruction(self):
        first, duplicate = await asyncio.gather(self.bridge.publish(self.request), self.bridge.publish(self.request))
        self.assertEqual(first, duplicate)
        replay = TurnBridge(SessionBridge(Path(self.temp.name)))
        self.assertEqual(first, await replay.publish(self.request))
        events = (await replay.events(self.cursor()))["events"]
        self.assertEqual([e["seq"] for e in events], [1, 2])
        self.assertEqual([e["type"] for e in events], ["sources", "done"])
        self.assertTrue(all(not e["content"] for e in events))
        self.assertEqual([e["seq"] for e in (await replay.events(self.cursor(after_seq=1)))["events"]], [2])
        self.assertEqual((await replay.events(self.cursor(after_seq=2)))["events"], [])
        with scoped_store(self.sessions, first["user_id"]) as store:
            self.assertEqual(await store.get_messages(first["session_id"]), [])

    async def test_same_revision_different_digest_is_rejected(self):
        await self.bridge.publish(self.request)
        with self.assertRaises(HTTPException) as raised:
            await self.bridge.publish(self.request.model_copy(update={"result_digest": "b" * 64}))
        self.assertEqual(raised.exception.status_code, 409)
        events = await self.bridge.events(self.cursor())
        self.assertEqual(events["events"][-1]["metadata"]["result_digest"], "a" * 64)

    async def test_student_session_course_and_revision_are_separate(self):
        original = await self.bridge.publish(self.request)
        for changes in ({"student_id": "b"}, {"session_id": "other"}, {"course_id": "other"}, {"task_revision": 4}):
            with self.assertRaises(HTTPException):
                await self.bridge.events(self.cursor(**changes))
            second = await self.bridge.publish(self.request.model_copy(update=changes))
            self.assertNotEqual(original["turn_id"], second["turn_id"])

    async def test_partial_copy_can_be_retried_after_next_turn(self):
        from deeptutor.services.session import SQLiteSessionStore
        with patch.object(SQLiteSessionStore, "append_events", side_effect=RuntimeError("injected interruption")):
            with self.assertRaises(RuntimeError):
                await self.bridge.publish(self.request)
        await self.bridge.publish(self.request.model_copy(update={"task_revision": 4}))
        recovered = await self.bridge.publish(self.request)
        self.assertEqual(recovered["last_seq"], 2)

    async def test_real_active_execution_is_never_cancelled_by_projection(self):
        from integrations.deeptutor.session_bridge import SessionBindingRequest
        binding = await self.sessions.bind(SessionBindingRequest(**self.request.model_dump(include=set(SessionBindingRequest.model_fields))))
        with scoped_store(self.sessions, binding["user_id"]) as store:
            running = await store.begin_turn(binding["session_id"], "chat")
        with self.assertRaises(HTTPException) as raised:
            await self.bridge.publish(self.request)
        self.assertEqual(raised.exception.status_code, 409)
        with scoped_store(self.sessions, binding["user_id"]) as store:
            self.assertEqual((await store.get_turn(running["id"]))["status"], "running")

    async def test_clarification_and_failure_outcomes(self):
        for revision, outcome in enumerate(("awaiting_clarification", "failed", "cancelled"), start=5):
            request = self.request.model_copy(update={"task_revision": revision, "outcome": outcome})
            result = await self.bridge.publish(request)
            with scoped_store(self.sessions, result["user_id"]) as store:
                expected = "completed" if outcome == "awaiting_clarification" else outcome
                self.assertEqual((await store.get_turn(result["turn_id"]))["status"], expected)
            events = await self.bridge.events(self.cursor(task_revision=revision))
            self.assertEqual(events["events"][-1]["metadata"]["outcome"], outcome)


if __name__ == "__main__":
    unittest.main()
