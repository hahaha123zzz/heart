"""章节教学不再走专用模板，复用公共执行器；按用户要求未执行。"""
from unittest.mock import Mock, patch

from agents.task_service import TaskService
from database.learning_tasks import LearningTaskRepository
from memory.memory_manager import MemoryManager
from models.chat_request import ChatRequest
from tests.test_q5_learning import Q5TestBase


class ChapterSharedExecutionTests(Q5TestBase):
    def test_chapter_request_reaches_executor_and_keeps_idempotency(self):
        memory = MemoryManager()
        memory.ensure_student('s', account_type='test')
        policy = Mock()
        policy.enabled.return_value = True
        policy.can_clarify.return_value = True
        policy.context = True
        tutor = Mock(memory=memory)
        service = TaskService(tutor, repository=LearningTaskRepository(), policy=policy)
        executor = Mock(return_value={'reply': '按教材开始讲解。',
            'answer_status': 'answered', 'step_advanced': False})
        request = ChatRequest(student_id='s', session_id='chapter-shared',
            request_id='chapter-shared-1', message='我想学习第一章的主要内容')
        with patch.dict('os.environ', {'INPUT_UNDERSTANDING_MODE': 'active', 'Q5_LEARNING_ENABLED': '0'}):
            result = service.run(request, executor)
            repeated = service.run(request, executor)
        executor.assert_called_once()
        self.assertEqual(result['reply'], '按教材开始讲解。')
        self.assertEqual(repeated['task_id'], result['task_id'])
        self.assertFalse(result['step_advanced'])
        self.assertEqual(executor.call_args.args[1].turn_route['chapter_id'], 1)
