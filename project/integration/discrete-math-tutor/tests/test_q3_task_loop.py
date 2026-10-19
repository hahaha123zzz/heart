"""Q3 任务级暂停/接续/重复答复/取消验证。"""
import tempfile
import unittest
from unittest.mock import Mock, patch

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from agents.task_service import TaskService
from database import database as db
from database.learning_tasks import LearningTaskRepository
from database.models import Base
from memory.memory_manager import MemoryManager
from models.chat_request import ChatRequest
from agents.agent_loop_service import run_agent_loop_turn
from agents.q3_navigation import StubLearningNavigator
from llm.client import ChatToolCall, ChatToolResult
from tests.test_q3_agent_loop import ScriptedLLM, final_round, tool_round


class LiveLoopExecutor:
    def __init__(self, llm, memory):
        self.llm = llm
        self.memory = memory
        self.navigator = StubLearningNavigator()
        self.calls = []

    def __call__(self, request, context, resolved, intercept, guard, progress, *, previous=None):
        self.calls.append(previous)
        from types import SimpleNamespace
        orchestrator = SimpleNamespace(llm=self.llm, memory=self.memory, quality_checker=None)
        return run_agent_loop_turn(
            orchestrator=orchestrator, request=request, context=context, guard=guard,
            progress=progress, previous=previous, navigator=self.navigator,
            publish_gate=lambda text, result: (True, ""), llm=self.llm)



class PausedExecutor:
    def __init__(self):
        self.calls = []

    def __call__(self, request, context, resolved, intercept, guard, progress, *, previous=None):
        self.calls.append({"message": request.message, "previous": previous})
        if previous is None:
            state = {
                "protocol_version": 1,
                "messages": [
                    {"role": "system", "content": "system"},
                    {"role": "user", "content": request.message},
                    {"role": "assistant", "content": "", "tool_calls": [
                        {"id": "ask", "type": "function",
                         "function": {"name": "ask_user", "arguments": "{}"}}]},
                    {"role": "tool", "tool_call_id": "ask", "content": "waiting"},
                ],
                "pending_tool_call_id": "ask",
                "pending_question": {"intro": None, "questions": [
                    {"id": "q1", "prompt": "你指哪种设计？", "options": [],
                     "header": None, "multi_select": False, "allow_free_text": True,
                     "placeholder": None}]},
                "rounds": 1, "exploration_rounds": 1, "settlement_rounds": 0,
                "tool_steps": 1, "sources": [], "target": None,
            }
            return {
                "reply": "你指哪种设计？",
                "answer_status": "awaiting_clarification",
                "clarification": {"mode": "ask_user", "ask_user": state["pending_question"],
                                  "questions": state["pending_question"]["questions"]},
                "loop_paused": True,
                "loop_state": state,
                "routing": {"status": "ok", "intent": "continue"},
                "step_advanced": False,
            }
        self.asserted_previous = previous
        return {"reply": "按被试内设计解释。", "answer_status": "answered",
                "loop_events": [], "routing": {"status": "ok"}, "step_advanced": False}


class TaskLoopPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            "sqlite:///" + self.temp.name.replace("\\", "/") + "/q3.db",
            connect_args={"check_same_thread": False})

        @event.listens_for(self.engine, "connect")
        def fk(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        self.db_patch = patch.object(
            db, "SessionLocal",
            sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False))
        self.db_patch.start()
        self.memory = MemoryManager()
        self.memory.ensure_student("s", account_type="test")
        self.tutor = Mock()
        self.tutor.memory = self.memory
        self.repository = LearningTaskRepository()
        policy = Mock()
        policy.enabled.return_value = True
        policy.can_clarify.return_value = True
        policy.context = True
        self.service = TaskService(self.tutor, repository=self.repository, policy=policy)

    def tearDown(self):
        self.db_patch.stop()
        self.engine.dispose()
        self.temp.cleanup()

    def test_pause_then_resume_uses_same_task_and_raw_answer(self):
        executor = PausedExecutor()
        first = self.service.run(
            ChatRequest(student_id="s", session_id="legacy", request_id="r1",
                        message="请比较这两种设计。"), executor)
        self.assertEqual(first["answer_status"], "awaiting_clarification")
        self.assertTrue(first["loop_paused"])
        pending = self.repository.pending("s", "legacy")
        self.assertEqual(pending["id"], first["task_id"])
        self.assertEqual(pending["context"]["loop_state"]["pending_tool_call_id"], "ask")

        second = self.service.run(
            ChatRequest(student_id="s", session_id="legacy", request_id="r2",
                        task_id=first["task_id"], task_revision=first["task_revision"],
                        message="被试内设计"), executor)
        self.assertEqual(second["answer_status"], "answered")
        self.assertEqual(executor.asserted_previous["_resume_answer"], "被试内设计")
        self.assertEqual(executor.asserted_previous["context"]["loop_state"]["pending_tool_call_id"], "ask")

    def test_repeating_answered_task_does_not_execute_again(self):
        executor = PausedExecutor()
        first = self.service.run(
            ChatRequest(student_id="s", session_id="legacy", request_id="r1",
                        message="请比较这两种设计。"), executor)
        self.service.run(
            ChatRequest(student_id="s", session_id="legacy", request_id="r2",
                        task_id=first["task_id"], task_revision=first["task_revision"],
                        message="被试内设计"), executor)
        calls = len(executor.calls)
        duplicate = self.service.run(
            ChatRequest(student_id="s", session_id="legacy", request_id="r3",
                        task_id=first["task_id"], task_revision=first["task_revision"],
                        message="被试内设计"), executor)
        self.assertEqual(duplicate["answer_status"], "task_conflict")
        self.assertEqual(len(executor.calls), calls)

    def test_agent_loop_service_pauses_and_resumes_through_task_service(self):
        llm = ScriptedLLM([
            tool_round(("ask_user", {"questions": [{"id": "q1", "prompt": "你指哪种设计？"}]})),
            final_round("按被试内设计解释。"),
        ])
        executor = LiveLoopExecutor(llm, self.memory)
        first = self.service.run(
            ChatRequest(student_id="s", session_id="legacy", request_id="r1",
                        message="请比较这两种设计。"), executor)
        self.assertEqual(first["answer_status"], "awaiting_clarification")
        self.assertEqual(first["clarification"]["mode"], "ask_user")
        second = self.service.run(
            ChatRequest(student_id="s", session_id="legacy", request_id="r2",
                        task_id=first["task_id"], task_revision=first["task_revision"],
                        message="被试内设计"), executor)
        self.assertEqual(second["answer_status"], "answered")
        self.assertEqual(second["reply"], "按被试内设计解释。")
        self.assertIsNotNone(second["conversation_id"])
        history = self.memory.get_history("s")
        self.assertTrue(any("按被试内设计解释" in row["content"] for row in history))
        self.assertEqual(executor.calls[1]["_resume_answer"], "被试内设计")
        resumed_messages = second["loop_state"]["messages"]
        tool_message = next(message for message in resumed_messages
                            if message.get("role") == "tool")
        self.assertIn("被试内设计", tool_message["content"])

    def test_ask_user_option_click_resumes_with_label(self):
        llm = ScriptedLLM([
            tool_round(("ask_user", {"questions": [{"id": "q1", "prompt": "你指哪种设计？",
                "options": [{"label": "被试间设计"}, {"label": "被试内设计"}]}]})),
            final_round("按被试内设计解释。"),
        ])
        executor = LiveLoopExecutor(llm, self.memory)
        first = self.service.run(
            ChatRequest(student_id="s", session_id="legacy", request_id="r1",
                        message="请比较这两种设计。"), executor)
        self.assertEqual([option["label"] for option in first["clarification"]["options"]],
                         ["被试间设计", "被试内设计"])
        second = self.service.run(
            ChatRequest(student_id="s", session_id="legacy", request_id="r2",
                        task_id=first["task_id"], task_revision=first["task_revision"],
                        message="第一个", selected_option="q1:1"), executor)
        self.assertEqual(second["answer_status"], "answered")
        self.assertEqual(executor.calls[1]["_resume_answer"], "被试内设计")
        tool_message = next(message for message in second["loop_state"]["messages"]
                            if message.get("role") == "tool")
        self.assertIn("被试内设计", tool_message["content"])
        self.assertIn("你指哪种设计", tool_message["content"])

    def test_cancelled_paused_task_cannot_resume(self):
        executor = PausedExecutor()
        first = self.service.run(
            ChatRequest(student_id="s", session_id="legacy", request_id="r1",
                        message="请比较这两种设计。"), executor)
        self.repository.cancel("s", "legacy", first["task_id"], first["task_revision"])
        calls = len(executor.calls)
        result = self.service.run(
            ChatRequest(student_id="s", session_id="legacy", request_id="r2",
                        task_id=first["task_id"], task_revision=first["task_revision"],
                        message="被试内设计"), executor)
        self.assertEqual(result["answer_status"], "task_conflict")
        self.assertEqual(len(executor.calls), calls)


if __name__ == "__main__":
    unittest.main()
