"""Q1-A：常规会话不再只取最近两个已完成任务。"""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from agents.task_service import TaskService
from models.chat_request import ChatRequest


class RecentRepository:
    def __init__(self, rows):
        self.rows = rows
        self.limit = None

    def recent(self, student_id, session_id, limit=2):
        self.limit = limit
        return self.rows[-limit:]


class TaskServiceContextTests(unittest.TestCase):
    def test_regular_session_uses_more_than_two_task_turns(self):
        rows = [
            {"id": "t%d" % index,
             "payload": {"message": "问题%d" % index, "session_id": "s1"},
             "result": {"reply": "回答%d" % index},
             "knowledge_point": "实验心理学"}
            for index in range(1, 9)
        ]
        memory = Mock()
        memory.get_active_goal.return_value = "实验心理学"
        memory.list_knowledge_points.return_value = []
        memory.get_profile.return_value = SimpleNamespace(preferences={})
        repository = RecentRepository(rows)
        service = TaskService(SimpleNamespace(memory=memory), repository=repository, policy=Mock())
        request = ChatRequest(student_id="s", message="继续解释", session_id="s1")

        context, _, _ = service._context(request)

        self.assertEqual(repository.limit, 12)
        self.assertEqual(len(context.history), 16)
        self.assertEqual(context.history[0]["content"], "问题1")
        self.assertEqual(context.history[-1]["content"], "回答8")

    def test_legacy_session_keeps_memory_history_budget(self):
        memory = Mock()
        memory.get_history.return_value = [{"role": "user", "content": "旧问题"},
                                          {"role": "assistant", "content": "旧回答"}]
        memory.get_active_goal.return_value = "实验心理学"
        memory.list_knowledge_points.return_value = []
        memory.get_profile.return_value = SimpleNamespace(preferences={})
        service = TaskService(SimpleNamespace(memory=memory), repository=RecentRepository([]), policy=Mock())
        request = ChatRequest(student_id="s", message="继续", session_id="legacy")

        context, _, _ = service._context(request)

        self.assertEqual([row["content"] for row in context.history], ["旧问题", "旧回答"])


if __name__ == "__main__":
    unittest.main()
