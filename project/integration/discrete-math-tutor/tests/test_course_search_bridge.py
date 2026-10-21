"""公共检索接线：后端和路径分离、跨章范围、关系候选隔离。"""
import unittest
from unittest.mock import Mock, patch
from agents.course_search import CourseSearch, association_context
from agents.q3_navigation import LearningTarget, SourceRef, NavigationDecision


class CourseSearchBridgeTests(unittest.TestCase):
    def test_cross_chapter_missing_original_is_rejected_before_model_check(self):
        from types import SimpleNamespace
        from agents.agent_loop import LoopResult
        from agents.agent_loop_service import _publish_gate
        result=LoopResult();result.sources=[{'chapter_id':2,'text':'只有第二章'}]
        tutor=Mock()
        gate=_publish_gate(tutor,SimpleNamespace(message='第一章和第二章的联系',student_id='isolated'),
                           LearningTarget('query','跨章'))
        passed,reason=gate('联系[1]',result)
        self.assertFalse(passed);self.assertIn('第1章',reason)
        tutor.quality_checker.check.assert_not_called()

    def setUp(self):
        self.target = LearningTarget('objective', '当前点', chapter_id=2, section_id=3)
        self.source = SourceRef('s1', 'doc', '教材原文', version='v1')
        self.base = Mock()
        self.base.resolve.return_value = NavigationDecision('teach', self.target)
        self.backend = Mock(last_result={'input_signature': 'frozen', 'graph_context': []})
        self.backend.search.return_value = [self.source]

    def test_q5_resolve_keeps_path_and_search_uses_injected_backend(self):
        search = CourseSearch(self.base, message='解释当前点', llm=Mock(), backend=self.backend)
        self.assertEqual(search.resolve(message='解释当前点').target, self.target)
        self.assertEqual(search.search(target=self.target, query='解释', limit=4), [self.source])
        self.base.search.assert_not_called()
        self.assertEqual(search.calls[0]['input_signature'], 'frozen')
        self.assertFalse(search.calls[0]['fallback'])

    def test_q5_entrypoint_does_not_replace_injected_backend(self):
        from types import SimpleNamespace
        from agents.agent_loop_service import run_agent_loop_turn
        from models.task_context import TaskContext
        from models.chat_request import ChatRequest
        from tests.test_q3_agent_loop import ScriptedLLM, tool_round, final_round
        llm=ScriptedLLM([tool_round(('retrieve_course', {'query':'当前点'})), final_round('讲解[1]')])
        q5=SimpleNamespace(service=Mock(),scope=Mock(),search=Mock(),
            loop_binding=lambda:{'target':self.target},status_line=lambda:'')
        with patch('agents.q5_learning.Q5Navigator',return_value=self.base):
            result=run_agent_loop_turn(orchestrator=SimpleNamespace(llm=llm,memory=None),
                request=ChatRequest(student_id='isolated',session_id='tab',request_id='q5-bridge',message='讲解当前点'),
                context=TaskContext(student_id='isolated',message='讲解当前点',knowledge_point='当前点'),q5=q5,navigator=self.backend,
                publish_gate=lambda *_:(True,''))
        self.assertEqual(result['answer_status'],'answered')
        self.base.resolve.assert_called_once();self.backend.search.assert_called_once()
        self.base.search.assert_not_called()
        self.assertTrue(result['retrieval_calls'])

    def test_explicit_cross_chapter_does_not_filter_to_current_section(self):
        search = CourseSearch(self.base, message='第一章的实验程序和第二章的自变量控制有哪些联系？',
                              llm=Mock(), backend=self.backend)
        search.search(target=self.target, query='实验程序与控制', limit=8)
        passed = self.backend.search.call_args.kwargs['target']
        self.assertIsNone(passed.chapter_id)
        self.assertIsNone(passed.section_id)
        self.assertEqual(self.target.section_id, 3)
        self.assertTrue(search.calls[0]['side_question'])

    def test_exact_target_keeps_q2_read_and_does_not_fallback_if_stale(self):
        target = LearningTarget('ch2:s3:b4', '真实范围', version='v1')
        search = CourseSearch(self.base, message='继续这个例子', llm=Mock(), backend=self.backend)
        with patch('knowledge.course_navigation.read_target', return_value=[]):
            with self.assertRaisesRegex(ValueError, '失效'):
                search.search(target=target, query='继续', limit=4)
        self.backend.search.assert_not_called()
        self.assertFalse(search.calls[0]['fallback'])

    def test_relation_requires_current_original_link_and_stays_ineligible(self):
        self.backend.last_result = {'graph_context': [
            {'kind': 'relationship', 'description': '候选联系', 'original_source_ids': ['s1']},
            {'kind': 'relationship', 'description': '无原文', 'original_source_ids': ['old']}]}
        rows = association_context(self.backend, [self.source])
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]['evidence_eligible'])
        self.assertEqual(rows[0]['original_sources'][0]['version'], 'v1')
        self.assertEqual(rows[0]['original_sources'][0]['document_id'], 'doc')

    def test_backend_failure_does_not_silently_use_old_search(self):
        self.backend.search.side_effect = RuntimeError('索引不可用')
        search = CourseSearch(self.base, message='解释', llm=Mock(), backend=self.backend)
        with self.assertRaises(RuntimeError):
            search.search(target=self.target, query='解释', limit=4)
        self.base.search.assert_not_called()
        self.assertEqual(search.calls[0]['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
