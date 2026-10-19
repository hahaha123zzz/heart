"""黄金集不能把 HTTP 200、模拟回答或错误引用当成已完成接入。"""
from copy import deepcopy
import unittest

from scripts.check_deeptutor_golden import checks_for


class GoldenChecksTests(unittest.TestCase):
    def setUp(self):
        self.case = {'kind': 'answer'}
        self.calls = [{'path': '/internal/heart/generate', 'ok': True, 'images': 0},
            {'path': '/internal/heart/knowledge/search', 'ok': True}]
        self.versions = {'book:1': 'version-1'}
        self.result = {'answer_status': 'answered', 'reply': '教材定义。[1]',
            'quality': {'passed': True, 'issues': []}, 'evidence_check': {'status': 'sufficient', 'mode': 'model'},
            'deeptutor_session': {'status': 'ready'}, 'deeptutor_turn': {'status': 'ready'},
            'pdf_references': [{'source_index': 0,
                'selection_ref': {'evidence_id': 'evidence-1', 'document_id': 'book:1', 'version': 'version-1'},
                'evidence': {'evidence_id': 'evidence-1', 'document_id': 'book:1', 'document_version': 'version-1',
                    'quote': '教材定义', 'location_status': 'exact'}}]}

    def check(self, result=None, calls=None, case=None):
        return checks_for(case or self.case, result or self.result, self.calls if calls is None else calls, self.versions)

    def test_real_canonical_answer_passes(self):
        self.assertTrue(all(self.check().values()))

    def test_mock_or_missing_provider_is_not_real_execution(self):
        self.assertFalse(self.check(calls=[])['real_gateway_used'])
        result = deepcopy(self.result); result['evidence_check']['mode'] = 'mock'
        self.assertFalse(self.check(result)['evidence_gate'])

    def test_unverified_quality_and_unknown_markers_fail(self):
        result = deepcopy(self.result); result['reply'] = '编造结论。[99]'; result['quality']['passed'] = False
        checks = self.check(result)
        self.assertFalse(checks['citation_ids']); self.assertFalse(checks['quality_passed'])
        result = deepcopy(self.result); result['pdf_references'].append(deepcopy(result['pdf_references'][0]))
        self.assertFalse(self.check(result)['citation_ids'])

    def test_changed_or_missing_document_identity_fails(self):
        for value in ({'document_id': 'other'}, {'version': 'old'}, {'document_id': None, 'version': None}):
            result = deepcopy(self.result); result['pdf_references'][0]['selection_ref'].update(value)
            self.assertFalse(self.check(result)['source_versions'])

    def test_hint_cannot_pass_as_full_answer(self):
        self.assertFalse(self.check(case={'kind': 'hint'})['hint_scope'])
        result = deepcopy(self.result)
        result.update(task_execution={'learning_intents': ['hint'], 'answer_constraints': ['hint_only']},
            teaching_plan={'action': 'give_hint'})
        self.assertTrue(self.check(result, case={'kind': 'hint'})['hint_scope'])
        result['teaching_plan']['action'] = 'explain'
        self.assertFalse(self.check(result, case={'kind': 'hint'})['hint_scope'])

    def test_refusal_must_stop_before_publishing(self):
        result = {'answer_status': 'evidence_rejected', 'evidence_check': {'status': 'partial', 'mode': 'model'}, 'step_advanced': False}
        self.assertTrue(all(self.check(result, case={'kind': 'refusal'}).values()))
        result['evidence_check']['mode'] = 'mock'
        self.assertFalse(self.check(result, case={'kind': 'refusal'})['insufficient_evidence'])
        self.assertFalse(self.check(case={'kind': 'refusal'})['refused'])

    def test_image_case_requires_actual_successful_image_transport(self):
        self.assertFalse(self.check(case={'kind': 'vision'})['images_sent'])
        calls = deepcopy(self.calls); calls[0]['images'] = 1
        self.assertTrue(self.check(calls=calls, case={'kind': 'vision'})['images_sent'])
        calls[0]['ok'] = False
        self.assertFalse(self.check(calls=calls, case={'kind': 'vision'})['images_sent'])

    def test_client_selection_text_leak_fails(self):
        calls = deepcopy(self.calls); calls[0]['client_text_leaked'] = True
        self.assertFalse(self.check(calls=calls)['no_client_text_leak'])


if __name__ == '__main__': unittest.main()
