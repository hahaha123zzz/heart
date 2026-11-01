"""验证跨层缺证和身份边界；不把模型构造成功当原文核验成功。"""
import unittest
from copy import deepcopy

from pydantic import ValidationError

from agents.q3_navigation import LearningTarget, SourceRef
from models.evidence_execution import EvidencePackage, EvidenceRequest


def request():
    return EvidenceRequest.model_validate({
        'request_id': 'req', 'decision_id': 'decision',
        'context': {'student_id': 'test', 'session_id': 'session', 'course_id': 'psychology',
                    'task_id': 'task', 'task_revision': 1},
        'documents': {'doc': 'version'},
        'requirements': [{'id': 'iv', 'query': '自变量定义'},
                         {'id': 'dv', 'query': '因变量定义'},
                         {'id': 'figure', 'query': '变量示意图', 'kind': 'image', 'required': False}],
        'constraints': ['no_questions'],
    })


def package_data():
    return dict(request=request(), status='completed', sources=[SourceRef('source', 'doc', '测试原文', version='version')],
                coverage=[{'requirement_id': name, 'status': 'satisfied', 'source_ids': ['source']}
                          for name in ('iv', 'dv')] +
                         [{'requirement_id': 'figure', 'status': 'missing', 'reason': '没有可用图像'}])


class EvidenceExecutionTests(unittest.TestCase):
    def test_optional_picture_does_not_block_complete_text(self):
        result = EvidencePackage(**package_data())
        self.assertTrue(result.ready_for_composition)
        self.assertEqual(result.missing_required, [])

    def test_missing_comparison_side_cannot_be_completed(self):
        data = package_data()
        data['coverage'][1] = {'requirement_id': 'dv', 'status': 'missing', 'reason': '未找到因变量'}
        with self.assertRaisesRegex(ValidationError, 'required_evidence_incomplete'):
            EvidencePackage(**data)
        data['status'] = 'partial'
        result = EvidencePackage(**data)
        self.assertFalse(result.ready_for_composition)
        self.assertEqual(result.missing_required, ['dv'])

    def test_cancelled_result_is_not_ready(self):
        data = package_data() | {'status': 'cancelled'}
        self.assertFalse(EvidencePackage(**data).ready_for_composition)

    def test_unknown_or_duplicate_coverage_is_rejected(self):
        for mutation in ('unknown', 'duplicate'):
            with self.subTest(mutation=mutation):
                data = package_data()
                if mutation == 'unknown':
                    data['coverage'][0]['source_ids'] = ['invented']
                else:
                    data['coverage'][1] = deepcopy(data['coverage'][0])
                with self.assertRaises(ValidationError):
                    EvidencePackage(**data)

    def test_wrong_version_and_stub_are_rejected(self):
        for source in (SourceRef('source', 'doc', '原文', version='old'),
                       SourceRef('source', 'doc', '原文', version='version', location={'stub': True})):
            with self.subTest(source=source):
                with self.assertRaises(ValidationError):
                    EvidencePackage(**(package_data() | {'sources': [source]}))

    def test_explicit_target_scope_is_kept(self):
        data = package_data()
        data['request'].requirements[0].target = LearningTarget('ch2', '第二章', chapter_id=2)
        with self.assertRaisesRegex(ValidationError, 'support_outside_target_scope'):
            EvidencePackage(**data)

    def test_image_caption_is_not_pixel_evidence(self):
        data = package_data()
        data['request'].requirements[0].kind = 'image'
        data['request'].requirements[0].pixels_required = True
        with self.assertRaisesRegex(ValidationError, 'pixel_evidence_required'):
            EvidencePackage(**data)

    def test_pixels_from_another_document_cannot_satisfy_requirement(self):
        data = package_data()
        data['request'].requirements[0].kind = 'image'
        data['request'].requirements[0].pixels_required = True
        data['sources'][0].image_refs.append({'model_saw_pixels': True, 'document_id': 'other', 'version': 'version'})
        with self.assertRaisesRegex(ValidationError, 'pixel_evidence_required'):
            EvidencePackage(**data)

    def test_matching_pixel_receipt_can_satisfy_requirement(self):
        data = package_data()
        data['request'].requirements[0].kind = 'image'
        data['request'].requirements[0].pixels_required = True
        data['sources'][0].image_refs.append({'model_saw_pixels': True, 'document_id': 'doc', 'version': 'version'})
        self.assertTrue(EvidencePackage(**data).ready_for_composition)

    def test_no_user_supplied_ready_flag_or_private_extra_field(self):
        for extra in ({'ready_for_composition': True}, {'grant': 'all'}):
            with self.assertRaises(ValidationError):
                EvidencePackage(**(package_data() | extra))

    def test_json_checkpoint_roundtrip(self):
        original = EvidencePackage(**package_data())
        restored = EvidencePackage.model_validate_json(__import__('json').dumps(original.checkpoint_payload()))
        self.assertEqual(original.model_dump(), restored.model_dump())


if __name__ == '__main__':
    unittest.main()
