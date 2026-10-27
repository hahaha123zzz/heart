"""隔离候选来源门禁：Q2版本/归属/范围变化不能成为可用证据。"""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch, Mock
from types import SimpleNamespace

from tests import test_native_learning_migration as fixtures
from integrations.deeptutor.learning_sources import check_candidate_sources


class NativeLearningSourcesTests(unittest.TestCase):
    setUp = fixtures.NativeLearningMigrationTests.setUp
    tearDown = fixtures.NativeLearningMigrationTests.tearDown
    make_plan = fixtures.NativeLearningMigrationTests.make_plan
    confirmed_plan = fixtures.NativeLearningMigrationTests.confirmed_plan
    candidate = fixtures.NativeLearningMigrationTests.candidate

    def source_case(self):
        snapshot = self.candidate()
        ref = {'source_kind': 'q2_navigation', 'unit_id': 'ch1:s1:b6', 'version': 'v1',
               'document_id': 'doc1', 'release_id': 'r1', 'source_version': 's1',
               'chapter_id': 1, 'section_id': 1, 'source_block_ids': [6, 7], 'target_schema': 'schema1'}
        for row in snapshot['objectives']:
            row['source_refs'] = json.dumps([ref])
        return snapshot, ref

    def check(self, snapshot, *, error=None, release='r1', schema='schema1'):
        unit = {'id': 'ch1:s1:b6', 'source_version': 's1', 'chapter_id': 1,
                'section_id': 1, 'source_block_ids': [6, 7], 'target_schema': schema}
        with patch('knowledge.course_config.COURSE_ID', 'course-1'), \
             patch('knowledge.course_navigation.validate', return_value=unit, side_effect=error) as validate, \
             patch('knowledge.course_release.validate', return_value={'release_id': release, 'ready': False}) as publish, \
             patch('knowledge.pdf_reader.document_for_chapter', return_value={'document_id': 'doc1'}):
            result = check_candidate_sources(snapshot)
            return result, validate.call_count, publish.call_count

    def test_current_sources_deduplicate_and_do_not_modify_snapshot_or_release_readiness(self):
        snapshot, _ = self.source_case()
        before = deepcopy(snapshot)
        result, calls, releases = self.check(snapshot)
        self.assertTrue(result['verified'])
        self.assertEqual((result['checked'], calls, releases), (1, 1, 1))
        self.assertFalse(result['release_ready'])
        self.assertEqual(snapshot, before)

    def test_legacy_unit_identity_is_supported_without_inventing_ranges(self):
        snapshot, ref = self.source_case()
        ref['source_block_ids'] = [ref['unit_id']]
        for row in snapshot['objectives']:
            row['source_refs'] = [ref]
        self.assertTrue(self.check(snapshot)[0]['verified'])

    def test_foreign_course_does_not_read_book(self):
        snapshot, _ = self.source_case()
        snapshot['path']['course_id'] = 'other'
        result, calls, releases = self.check(snapshot)
        self.assertFalse(result['verified'])
        self.assertEqual((calls, releases), (0, 0))

    def test_missing_identity_and_changed_document_range_release_fail_closed(self):
        for key, value, reason in (
            ('release_id', '', 'source_identity_incomplete'),
            ('release_id', 'old', 'release_changed'),
            ('source_kind', 'selection', 'source_identity_incomplete'),
            ('document_id', 'other', 'source_identity_changed'),
            ('source_version', 'old', 'source_identity_changed'),
            ('chapter_id', 2, 'source_identity_changed'),
            ('section_id', 2, 'source_identity_changed'),
            ('source_block_ids', [6], 'source_range_changed'),
            ('source_block_ids', '6', 'source_range_changed'),
            ('target_schema', 'old', 'target_schema_changed'),
            ('source_valid', False, 'source_unavailable'),
        ):
            with self.subTest(key=key):
                snapshot, ref = self.source_case()
                ref[key] = value
                for row in snapshot['objectives']:
                    row['source_refs'] = [ref]
                result = self.check(snapshot)[0]
                self.assertFalse(result['verified'])
                self.assertEqual(result['issues'][0]['reason'], reason)

    def test_q2_missing_or_changed_source_is_not_an_empty_success(self):
        snapshot, _ = self.source_case()
        for error in (ValueError('changed'), FileNotFoundError('missing')):
            with self.subTest(error=error):
                result = self.check(snapshot, error=error)[0]
                self.assertFalse(result['verified'])
                self.assertEqual(result['issues'][0]['reason'], 'source_unavailable')

    def test_recheck_does_not_reuse_previous_success(self):
        snapshot, _ = self.source_case()
        self.assertTrue(self.check(snapshot)[0]['verified'])
        result = self.check(snapshot, release='r2')[0]
        self.assertFalse(result['verified'])
        self.assertEqual(result['issues'][0]['reason'], 'release_changed')

    def test_known_legacy_schema_alias_requires_same_version_and_exact_unit(self):
        snapshot, ref = self.source_case()
        ref.update(target_schema='q2.teaching_targets.v1', source_block_ids=[ref['unit_id']])
        for row in snapshot['objectives']:
            row['source_refs'] = [ref]
        self.assertTrue(self.check(snapshot, schema='word-heading-targets-v1')[0]['verified'])
        self.assertFalse(self.check(snapshot, schema='word-heading-targets-v2')[0]['verified'])
        self.assertFalse(self.check(snapshot, schema='word-heading-targets-v1', error=ValueError('changed'))[0]['verified'])
        ref['source_block_ids'] = [6, 7]
        self.assertFalse(self.check(snapshot, schema='word-heading-targets-v1')[0]['verified'])

    def test_new_chapter_plan_uses_q2_schema_instead_of_legacy_literal(self):
        from agents.q5_runtime import Q5Runtime
        service = SimpleNamespace(create_plan=Mock(return_value={}))
        runtime = SimpleNamespace(service=service, scope=None, status=lambda: {})
        unit = {'id': 'ch1:s1:b6', 'chapter_id': 1, 'section_id': 1, 'version': 'v1',
                'target_schema': 'word-heading-targets-v2'}
        with patch('knowledge.course_navigation.outline', return_value=[unit]), \
             patch('knowledge.course_release.binding', return_value={'release_id': 'r1'}), \
             patch('knowledge.pdf_reader.document_for_chapter', return_value={'document_id': 'doc1'}):
            Q5Runtime.propose_chapter_plan(runtime, '章节导学', 'cmd1')
        draft = service.create_plan.call_args.args[1]
        self.assertEqual(draft.modules[0][2][0].source_refs[0]['target_schema'], 'word-heading-targets-v2')


if __name__ == '__main__':
    unittest.main()
