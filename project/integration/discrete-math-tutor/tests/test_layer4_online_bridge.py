"""第四阶段调用链回归；模型响应为可控夹具，不宣称真实模型语义验收。"""
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from agents.course_search import CourseSearch, shared_search
from agents.object_evidence import requested_objects, missing_objects
from agents.q3_navigation import LearningTarget, SourceRef


class OnlineObjectTests(unittest.TestCase):
    def setUp(self):
        self.identity = 'experimental-psychology-3:chapter-02:b30'
        self.source = SourceRef('raw', 'experimental-psychology-3:chapter-02', '教材真实对象的完整文字',
            version='v', chapter_id=2, section_id=1,
            location={'object_id': self.identity, 'block_start': 30, 'source': '教材.txt', 'location_status': 'exact'})
        self.selected = replace(self.source, source_id='verified', location={**self.source.location,
            'evidence': {'location_status': 'exact', 'source_block_id': 30, 'block_start': 0, 'block_end': len(self.source.text)}})
        self.target = LearningTarget('ch1:s1:b2', '当前学习目标', chapter_id=1, section_id=1, version='old-target')
        self.base = Mock()

    def search(self, selected=None, *, cancellation=None, limit=6):
        search = CourseSearch(self.base, message='请解释教材表格 '+self.identity, llm=Mock(), cancellation=cancellation)
        with (patch('agents.object_evidence.read_requested_objects', return_value=([self.source], [self.source])),
              patch.object(search, 'select', return_value=[self.selected] if selected is None else selected) as select,
              patch('knowledge.course_navigation.read_target', side_effect=AssertionError('不能读取旧学习目标'))):
            result = search.search(target=self.target, query='模型改写的问题', limit=limit)
        return result, search, select

    def test_object_uses_original_selection_once_without_old_target_or_semantic_fallback(self):
        sources, search, select = self.search()
        self.assertEqual([s.source_id for s in sources], [self.selected.source_id])
        self.assertEqual(sources[0].location['retrieval_requirements'], ['object-1'])
        select.assert_called_once()
        self.base.search.assert_not_called()
        self.assertEqual(search.calls[-1]['actual_backend'], 'q2_object')
        self.assertEqual(self.target.target_id, 'ch1:s1:b2')
        self.assertFalse(search.calls[-1]['formula_semantic_verified'])

    def test_neighbor_only_or_partial_object_cannot_be_reported_complete(self):
        for selected in ([], [replace(self.selected, location={'evidence': {
                'location_status': 'exact', 'source_block_id': 29, 'block_start': 0, 'block_end': len(self.source.text)}})],
                [replace(self.selected, text=self.source.text[:3], location={'evidence': {
                    'location_status': 'exact', 'source_block_id': 30, 'block_start': 0, 'block_end': 3}})]):
            with self.subTest(selected=selected):
                sources, search, _ = self.search(selected)
                self.assertEqual(sources, [])
                self.assertEqual(search.calls[-1]['missing_objects'], [self.identity])

    def test_failed_read_does_not_fallback(self):
        search = CourseSearch(self.base, message=self.identity, llm=Mock())
        with patch('agents.object_evidence.read_requested_objects', side_effect=ValueError('stale_version')):
            with self.assertRaisesRegex(ValueError, 'stale_version'):
                search.search(target=self.target, query='解释', limit=6)
        self.base.search.assert_not_called()
        self.assertEqual(search.calls[-1]['status'], 'failed')

    def test_other_active_course_cannot_read_psychology_object(self):
        search = CourseSearch(self.base, message=self.identity, llm=Mock())
        with (patch('knowledge.course_config.PSYCHOLOGY', False),
              patch('agents.object_evidence.read_requested_objects') as read):
            with self.assertRaisesRegex(ValueError, '不授权'):
                search.search(target=self.target, query='解释', limit=6)
        read.assert_not_called()
        self.base.search.assert_not_called()

    def test_cancel_after_read_never_selects_or_returns_material(self):
        token = Mock()
        token.check.side_effect = [None, None, RuntimeError('cancelled')]
        with self.assertRaisesRegex(RuntimeError, 'cancelled'):
            self.search(cancellation=token)
        self.base.search.assert_not_called()

    def test_two_objects_cannot_fit_one_result(self):
        search = CourseSearch(self.base, message=self.identity+' 与 '+self.identity.replace('b30', 'b31'), llm=Mock())
        with self.assertRaisesRegex(ValueError, '预算不足'):
            search.search(target=self.target, query='解释', limit=1)
        self.base.search.assert_not_called()

    def test_fabricated_version_or_gapped_ranges_do_not_cover_object(self):
        old = replace(self.selected, version='old')
        self.assertEqual(missing_objects([self.source], [old]), [self.identity])
        chunks = [replace(self.selected, text=self.source.text[a:b], location={'evidence': {
            'location_status': 'exact', 'source_block_id': 30, 'block_start': a, 'block_end': b}}) for a, b in ((0, 2), (4, len(self.source.text)))]
        self.assertEqual(missing_objects([self.source], chunks), [self.identity])

    def test_invalid_or_forged_range_is_rejected(self):
        for start, end in ((-1, 20), (0, 999), (0, 2)):
            selected = replace(self.selected, location={'evidence': {
                'location_status': 'exact', 'source_block_id': 30, 'block_start': start, 'block_end': end}})
            with self.assertRaisesRegex(ValueError, '原文范围不一致'):
                missing_objects([self.source], [selected])

    def test_unlocated_original_cannot_be_upgraded_by_cached_index(self):
        original = replace(self.source, location={**self.source.location, 'location_status': 'unlocated'})
        search = CourseSearch(self.base, message=self.identity, llm=Mock())
        with (patch('agents.object_evidence.read_requested_objects', return_value=([original], [original])),
              patch.object(search, 'select') as select):
            self.assertEqual(search.search(target=self.target, query='解释', limit=6), [])
        select.assert_not_called()
        self.assertEqual(search.coverage_report['status'], 'partial')
        self.assertEqual(missing_objects([original], [self.selected]), [self.identity])

    def test_section_evidence_cannot_replace_exact_object_range(self):
        selected = replace(self.selected, location={**self.selected.location,
            'evidence': {**self.selected.location['evidence'], 'location_status': 'section'}})
        self.assertEqual(missing_objects([self.source], [selected]), [self.identity])

    def test_object_interjection_reaches_q5_and_selection_callers(self):
        from agents.course_search import question_interjection
        self.assertTrue(question_interjection('请解释'+self.identity, self.target))
        self.assertTrue(question_interjection(' '.join(self.identity.replace('b30', 'b'+str(i)) for i in range(3)), self.target))
        self.assertFalse(question_interjection('继续这个例子', self.target))

    def test_two_object_tags_reach_existing_publication_gate(self):
        from agents.agent_loop import LoopResult
        from agents.agent_loop_service import _publish_gate
        other = replace(self.source, source_id='raw2', location={**self.source.location,
            'object_id': self.identity.replace('b30', 'b31'), 'block_start': 31})
        selected_other = replace(self.selected, source_id='verified2', location={**other.location,
            'evidence': {**self.selected.location['evidence'], 'source_block_id': 31}})
        message = self.identity+' 与 '+other.location['object_id']
        navigation = CourseSearch(self.base, message=message, llm=Mock())
        with (patch('agents.object_evidence.read_requested_objects', return_value=([self.source, other], [self.source, other])),
              patch.object(navigation, 'select', return_value=[self.selected, selected_other])):
            sources = navigation.search(target=self.target, query=message, limit=6)
        self.assertEqual(navigation.coverage_report['covered'], ['object-1', 'object-2'])
        self.assertEqual(navigation.tool_context(sources)['coverage'], navigation.coverage_report)
        state = LoopResult()
        # 本用例只检查既有“双方引用”门禁；原文核验另由真实教材专项执行。
        state.sources = [dict(s.to_dict(), index=i, location={'retrieval_requirements': s.location['retrieval_requirements']})
                         for i, s in enumerate(sources, 1)]
        gate = _publish_gate(SimpleNamespace(), SimpleNamespace(message=message), self.target, navigation)
        self.assertFalse(gate('只引用第一侧[1]', state)[0])
        self.assertTrue(gate('第一侧[1]，第二侧[2]', state)[0])

    def test_object_id_dedup_and_budget(self):
        self.assertEqual(requested_objects(self.identity+' '+self.identity), [self.identity])
        with self.assertRaisesRegex(ValueError, '最多读取两个'):
            requested_objects(' '.join(self.identity.replace('b30', 'b'+str(i)) for i in range(3)))


class OnlineCoverageTests(unittest.TestCase):
    @patch.dict('os.environ', {'Q3_RETRIEVAL_MODE': 'local'})
    def test_local_natural_comparison_uses_per_need_semantic_selection_and_retains_gap(self):
        from tests.test_lightrag_coverage import ref
        base = Mock(last_result=None)
        base.calls = []
        base.search.side_effect = lambda **kwargs: [ref('iv', 2)]
        message = '第二章的自变量和因变量有什么区别？'
        search = shared_search(base, message=message, llm=Mock())
        self.assertIsNotNone(search.coverage)
        def select(query, rows, *, subproblem='single', coverage=None):
            accepted = rows if coverage.query == '自变量' else []
            return accepted, {'source_ids': [r.source_id for r in accepted], 'reason': '对应原文' if accepted else '缺少因变量定义'}
        with patch.object(search, 'select', side_effect=select) as checked:
            sources = search.search(target=LearningTarget('current', '当前点', 2, 1), query=message, limit=6)
            cached = search.search(target=LearningTarget('current', '当前点', 2, 1), query='再查一次', limit=6)
        self.assertEqual(search.coverage_report['status'], 'partial')
        self.assertEqual(len(search.coverage_report['missing']), 1)
        self.assertIn('因变量', search.coverage_report['missing'][0]['query'])
        self.assertEqual(sources, cached)
        self.assertEqual(checked.call_count, 3)
        self.assertEqual(base.search.call_count, 3)
        self.assertEqual(sources[0].location['retrieval_requirements'], ['object-1'])
        self.assertTrue(search.calls[-1]['cached_coverage'])

    @patch.dict('os.environ', {'Q3_RETRIEVAL_MODE': 'local'})
    def test_simple_definition_does_not_add_coverage_model_calls(self):
        base = Mock()
        search = shared_search(base, message='什么是自变量？', llm=Mock())
        self.assertIsNone(search.coverage)


if __name__ == '__main__':
    unittest.main()
