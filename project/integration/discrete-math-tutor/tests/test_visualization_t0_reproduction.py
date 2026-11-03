"""普通教学对话未排队图解的隔离复现；修复后移除expectedFailure。"""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from agents.agent_loop_service import run_agent_loop_turn
from agents.q3_navigation import LearningTarget, StubLearningNavigator
from models.chat_request import ChatRequest
from models.task_context import TaskContext
from tests.test_learning_cards import STEPS
from tests.test_q3_q4_integration import FakeMemory, ScriptedLLM, tool_round


class NormalChatVisualizationReproduction(unittest.TestCase):
    @patch.dict('os.environ', {'RESPONSE_COMPOSITION_ENABLED': '1',
                               'ADAPTIVE_TUTORING_ENABLED': '1',
                               'Q5_LEARNING_ENABLED': '0',
                               'VISUALIZATION_ON_DEMAND': '1'})
    def test_answered_normal_turn_schedules_visualization(self):
        message = '直接解释变量，并分步展开'
        model = ScriptedLLM([tool_round('teaching_step', dict(
            strategy='explain', summary='先操纵再测量',
            card_kind='step_reveal', explanation_steps=STEPS))])
        request = ChatRequest(student_id='isolated', session_id='test', request_id='visual-t0', message=message)
        context = TaskContext(student_id='isolated', session_id='test', message=message, knowledge_point='自变量')
        jobs = []
        with patch('agents.tools.first_wave_runtime.bind_resources', return_value=(None, ())), \
             patch('agents.adaptive_tutoring.verified_sources', side_effect=lambda rows: deepcopy(rows)), \
             patch('visualization.on_demand.build_guide') as build:
            build.side_effect = lambda *args, **kwargs: kwargs['deferred'].append(lambda: {'frames': []})
            result = run_agent_loop_turn(
                orchestrator=SimpleNamespace(llm=model, memory=FakeMemory(), quality_checker=None),
                request=request, context=context, navigator=StubLearningNavigator(target=LearningTarget('target', '自变量')),
                publish_gate=lambda *_: (True, ''), visualization_jobs=jobs)
        self.assertEqual(result['answer_status'], 'answered')
        self.assertEqual(len(jobs), 1, '普通教学回答没有排队图解任务')


if __name__ == '__main__':
    unittest.main()
