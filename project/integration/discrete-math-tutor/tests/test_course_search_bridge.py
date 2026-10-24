"""公共检索接线：后端和路径分离、跨章范围、关系候选隔离。"""
import unittest
from unittest.mock import Mock, patch
from agents.course_search import CourseSearch, association_context
from agents.q3_navigation import LearningTarget, SourceRef, NavigationDecision


class CourseSearchBridgeTests(unittest.TestCase):
    def test_new_concept_question_does_not_inherit_reader_scope(self):
        target = LearningTarget('kp:history', '第二节 实验心理学的产生与发展', chapter_id=1, section_id=2)
        search = CourseSearch(self.base, message='给我解释一下被试反应', llm=Mock(), backend=self.backend)
        search.search(target=target, query='被试反应', limit=6)
        passed = self.backend.search.call_args.kwargs['target']
        self.assertIsNone(passed.section_id)
        self.assertIsNone(passed.chapter_id)
        self.assertEqual((target.chapter_id, target.section_id), (1, 2))

    def test_plain_question_uses_chapter_preference_without_section_lock(self):
        search = CourseSearch(self.base, message='被试反应有哪些形式？', llm=Mock(), backend=self.backend)
        search.search(target=self.target, query='反应形式', limit=6)
        passed = self.backend.search.call_args.kwargs['target']
        self.assertIsNone(passed.section_id)
        self.assertEqual(passed.chapter_id, self.target.chapter_id)
        self.assertTrue(passed.source_scope['allow_course_expansion'])

    def test_figure_reads_original_without_semantic_backend(self):
        from knowledge.figure_reading import named_figures, read_figure
        figures = named_figures('图1-4讲的是什么')
        if not figures:
            self.skipTest('没有心理学原图输入')
        chunk = read_figure(figures[0])[0]
        self.assertEqual((chunk.chapter_id, chunk.section_id), (1, 3))
        self.assertIn('图1-4', chunk.text)
        self.assertTrue(chunk.source_spans)
        search = CourseSearch(self.base, message='图1-4讲的是什么', llm=Mock(), backend=self.backend)
        with patch.object(search, 'select', side_effect=lambda question, rows: rows):
            sources = search.search(target=self.target, query='图1-4 冯特', limit=6)
        self.assertTrue(sources)
        self.assertEqual(sources[0].section_id, 3)
        self.backend.search.assert_not_called()
        self.assertEqual(search.calls[-1]['actual_backend'], 'q2_figure')

    def test_missing_or_duplicate_figure_never_uses_wrong_text(self):
        search = CourseSearch(self.base, message='图1-4讲的是什么', llm=Mock(), backend=self.backend)
        figure = Mock(label='图1-4', id='duplicate')
        for found in ([], [figure, figure]):
            with patch('knowledge.figure_reading.named_figures', return_value=found):
                self.assertEqual(search.search(target=self.target, query='图1-4', limit=6), [])
        self.backend.search.assert_not_called()

    def test_continuing_derivation_keeps_exact_q2_scope(self):
        from agents.course_search import question_interjection
        target = LearningTarget('ch1:s2:b3', '当前目标', chapter_id=1, section_id=2)
        for message in ['下一步推导', '继续这个例子', '解释一下当前目标', '没听懂，换个说法']:
            self.assertFalse(question_interjection(message, target), message)

    def test_new_concept_turn_has_no_q5_write_tools(self):
        from types import SimpleNamespace
        from agents.agent_loop_service import run_agent_loop_turn
        from agents.tool_protocol import ToolDefinition
        from models.task_context import TaskContext
        from models.chat_request import ChatRequest
        from tests.test_q3_agent_loop import ScriptedLLM, final_round
        llm = ScriptedLLM([final_round('插问回复')])
        q5 = SimpleNamespace(service=Mock(), scope=Mock(), search=Mock(), status_line=lambda: '',
            loop_binding=lambda: {'target': self.target, 'tool_instances': [
                SimpleNamespace(definition=ToolDefinition('mastery_understood', '修改位置'))]})
        message = '给我解释一下被试反应'
        with patch('agents.q5_learning.Q5Navigator', return_value=self.base):
            result = run_agent_loop_turn(orchestrator=SimpleNamespace(llm=llm, memory=None),
                request=ChatRequest(student_id='isolated', request_id='concept-side', message=message),
                context=TaskContext(student_id='isolated', message=message), q5=q5, navigator=self.backend,
                publish_gate=lambda *_: (True, ''))
        self.assertTrue(result['learning_interjection'])
        self.assertNotIn('mastery_understood', [t['function']['name'] for t in llm.calls[0]['tools']])

    def test_per_object_selection_is_not_globally_dropped_or_repeated(self):
        from knowledge.lightrag.coverage import CoverageNavigator
        from tests.test_lightrag_coverage import ref
        backend=Mock(last_result={'graph_context':[]});backend.calls=[]
        backend.search.side_effect=lambda **kw:[ref('s'+str(kw['target'].chapter_id),kw['target'].chapter_id)]
        search=CourseSearch(self.base,message='第一章的实验程序和第二章的自变量控制有哪些联系？',llm=Mock(),backend=backend)
        search.coverage=CoverageNavigator(backend,question=search.message,select=lambda req,rows:rows,
            judge=lambda req,rows:{'source_ids':[r.source_id for r in rows],'reason':'对应对象原文'})
        with patch.object(search,'select',side_effect=AssertionError('不能合并后再全局筛选')):
            first=search.search(target=self.target,query='两章联系',limit=4)
            second=search.search(target=self.target,query='重新查两章',limit=4)
        self.assertEqual({r.chapter_id for r in first},{1,2});self.assertEqual(first,second)
        self.assertEqual(backend.search.call_count,2)
        self.assertEqual(search.coverage_report['status'],'covered')
        self.assertTrue(search.calls[-1]['cached_coverage'])

    def test_q5_source_pointer_is_read_without_changing_objective_identity(self):
        target=LearningTarget('objective-id','当前目标',source_scope={'source_refs':[
            {'source_kind':'q2_navigation','unit_id':'ch1:s1:b6','version':'version'}]})
        search=CourseSearch(self.base,message='继续这个例子',llm=Mock(),backend=self.backend)
        with patch('knowledge.course_navigation.read_target',return_value=[]) as read:
            with self.assertRaisesRegex(ValueError,'失效'):
                search.search(target=target,query='解释',limit=4)
        read.assert_called_once_with({'id':'ch1:s1:b6','version':'version'})
        self.backend.search.assert_not_called();self.assertEqual(target.target_id,'objective-id')

    def test_covered_sources_must_both_be_used_in_final_citations(self):
        from types import SimpleNamespace
        from agents.agent_loop import LoopResult
        from agents.agent_loop_service import _publish_gate
        state=LoopResult();state.sources=[
            {'chapter_id':1,'index':1,'text':'实验程序','location':{'retrieval_requirements':['object-1']}},
            {'chapter_id':2,'index':2,'text':'自变量控制','location':{'retrieval_requirements':['object-2']}}]
        navigation=SimpleNamespace(coverage_report={'status':'covered','covered':['object-1','object-2']})
        tutor=SimpleNamespace(quality_checker=None,memory=None)
        gate=_publish_gate(tutor,SimpleNamespace(message='第一章和第二章的联系'),self.target,navigation)
        self.assertFalse(gate('只讲第一方[1]',state)[0])
        self.assertTrue(gate('第一方[1]，第二方[2]',state)[0])

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
        self.backend.calls = []

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
        llm=ScriptedLLM([final_round('学习路径：路径 · 当前目标：**当前点**\n\n讲解[1]')])
        q5=SimpleNamespace(service=Mock(),scope=Mock(),search=Mock(),
            loop_binding=lambda:{'target':self.target},status_line=lambda:'学习路径：路径 · 当前目标：当前点')
        with patch('agents.q5_learning.Q5Navigator',return_value=self.base):
            result=run_agent_loop_turn(orchestrator=SimpleNamespace(llm=llm,memory=None),
                request=ChatRequest(student_id='isolated',session_id='tab',request_id='q5-bridge',message='讲解当前点'),
                context=TaskContext(student_id='isolated',message='讲解当前点',knowledge_point='当前点'),q5=q5,navigator=self.backend,
                publish_gate=lambda *_:(True,''))
        self.assertEqual(result['answer_status'],'answered')
        self.base.resolve.assert_called_once();self.backend.search.assert_called_once()
        self.base.search.assert_not_called()
        self.assertTrue(result['retrieval_calls'])
        self.assertEqual(len(llm.calls),1)
        self.assertEqual(llm.calls[0]['tools'],[])
        self.assertEqual(result['reply'].count('学习路径：'),1)

    def test_cross_chapter_turn_has_no_q5_write_tools(self):
        from types import SimpleNamespace
        from agents.agent_loop_service import run_agent_loop_turn
        from agents.tool_protocol import ToolDefinition
        from models.task_context import TaskContext
        from models.chat_request import ChatRequest
        from tests.test_q3_agent_loop import ScriptedLLM, final_round
        llm=ScriptedLLM([final_round('插问回复')])
        q5=SimpleNamespace(service=Mock(),scope=Mock(),search=Mock(),status_line=lambda:'',
            loop_binding=lambda:{'target':self.target,'tool_instances':[
                SimpleNamespace(definition=ToolDefinition('mastery_understood','修改位置'))]})
        message='第一章的实验程序和第二章的自变量控制有哪些联系？'
        with patch('agents.q5_learning.Q5Navigator',return_value=self.base):
            result=run_agent_loop_turn(orchestrator=SimpleNamespace(llm=llm,memory=None),
                request=ChatRequest(student_id='isolated',request_id='side',message=message),
                context=TaskContext(student_id='isolated',message=message),q5=q5,navigator=self.backend,
                publish_gate=lambda *_:(True,''))
        self.assertTrue(result['learning_interjection'])
        names=[tool['function']['name'] for tool in llm.calls[0]['tools']]
        self.assertNotIn('mastery_understood',names)
        self.assertEqual(self.target.target_id,'objective')

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
