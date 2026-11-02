"""KC review and measurement contracts; reviewed records here are synthetic fixtures."""
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from knowledge.kc_registry import KCRegistry, REGISTRY_PATH, assessment_fingerprint, registry_fingerprint, validate_registry


class KCRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        document = {'chapter_id': 1, 'blocks': [{'block_index': 1, 'section_id': 1}]}
        (self.root / 'doc.json').write_text(json.dumps(document), encoding='utf-8')
        (self.root / 'book.docx').write_bytes(b'test textbook fixture')
        digest = lambda name: hashlib.sha256((self.root / name).read_bytes()).hexdigest()
        source = {'id': 'src', 'document': 'doc.json', 'docx': 'book.docx',
                  'document_sha256': digest('doc.json'), 'docx_sha256': digest('book.docx'),
                  'chapter_id': 1, 'section_id': 1, 'block_ids': [1]}
        item = lambda name: {'id': name, 'name': name, 'aliases': ['共同名称'], 'observable': name,
            'status': 'reviewed', 'reviewer': 'synthetic-test-reviewer',
            'source_refs': [{'source_id': 'src', 'block_ids': [1]}]}
        self.data = {'schema': 'kc-registry-v1', 'course_id': 'fixture', 'version': 'v1',
                     'sources': [source], 'knowledge_components': [item('a'), item('b')],
                     'relations': [], 'target_mappings': [{'target_id': 'topic-1', 'target_version': 'v1',
                         'kc_ids': ['a'], 'source_id': 'src', 'status': 'reviewed', 'reviewer': 'synthetic'}],
                     'assessment_mappings': []}
        self.target = {'id': 'topic-1', 'version': 'v1', 'source_valid': True}

    def registry(self):
        return KCRegistry(self.data, self.root, lambda target_id: self.target if target_id == self.target['id'] else None)

    def add_assessment(self):
        question, key, rubric = {'id': 'q1', 'text': '题面'}, {'answer': 'A'}, {'c1': '判断', 'c2': '解释'}
        self.data['target_mappings'][0]['kc_ids'] = ['a', 'b']
        mapping = {'registry_version': 'v1', 'registry_fingerprint': registry_fingerprint(self.data),
                   'target_id': 'topic-1', 'target_version': 'v1', 'criteria': {
            'c1': {'targeted_kcs': ['a', 'b'], 'evaluated_kcs': ['a', 'b']},
            'c2': {'targeted_kcs': ['a', 'b'], 'evaluated_kcs': ['b']}}}
        record = {'id': 'assessment-1', 'status': 'reviewed', 'reviewer': 'synthetic', 'mapping': mapping,
                  'fingerprint': assessment_fingerprint(question, key, rubric, mapping)}
        self.data['assessment_mappings'].append(record)
        return question, key, rubric, record

    def test_real_candidates_have_traceable_sources_but_do_not_project(self):
        registry = KCRegistry.load()
        source_present = all((REGISTRY_PATH.parent / path).is_file() for path in (
            'chapters/chapter_01/document.json', 'chapters/chapter_01/第1章实验心理学概论.docx'))
        self.assertEqual(registry.audit_sources()['chapter-01-variable-blocks'], source_present)
        self.assertEqual(registry.target_kcs('ch1:s3:b320'), [])
        self.assertEqual(registry.evaluated_coverage('unknown', question={}, answer_key={}, rubric={}, verdicts={}), [])
        self.assertEqual(registry.find_alias('自变量识别')[0]['status'], 'candidate')

    def test_stable_id_across_paths_and_ambiguous_aliases(self):
        self.data['relations'] = [{'from': 'a', 'to': 'b', 'type': 'related_to'}]
        registry = self.registry()
        self.assertEqual(registry.target_kcs('topic-1'), ['a'])
        ref = {'unit_id': 'topic-1', 'version': 'v1'}
        self.assertEqual(registry.path_objective_kcs([ref]), ['a'])
        self.assertEqual(registry.path_objective_kcs([dict(ref)]), ['a'])
        self.assertEqual(registry.path_objective_kcs([dict(ref, version='old')]), [])
        self.assertEqual({item['id'] for item in registry.find_alias('共同名称')}, {'a', 'b'})
        self.assertEqual([item['id'] for item in registry.find_alias('a')], ['a'])

    def test_stale_target_or_source_abstains(self):
        registry = self.registry()
        self.target['version'] = 'old'
        self.assertEqual(registry.target_kcs('topic-1'), [])
        self.target.update(version='v1', source_valid=False)
        self.assertEqual(registry.target_kcs('topic-1'), [])
        self.target['source_valid'] = True
        (self.root / 'book.docx').write_bytes(b'changed')
        self.assertFalse(registry.audit_sources()['src'])
        self.assertEqual(registry.target_kcs('topic-1'), [])

    def test_criteria_do_not_duplicate_an_entire_question_score(self):
        question, key, rubric, _ = self.add_assessment()
        registry = self.registry()
        run = lambda: registry.evaluated_coverage('assessment-1', question=question, answer_key=key,
                         rubric=rubric, verdicts={'c1': 'met', 'c2': 'partial'})
        self.assertEqual(run(), [{'criterion_id': 'c2', 'kc_id': 'b', 'verdict': 'partial'}])
        (self.root / 'doc.json').write_text('{}', encoding='utf-8')
        self.assertEqual(run(), [])

    def test_any_assessment_artifact_or_mapping_change_abstains(self):
        question, key, rubric, record = self.add_assessment()
        def run(data, q=question, k=key, r=rubric):
            return KCRegistry(data, self.root, lambda target_id: self.target).evaluated_coverage('assessment-1', question=q, answer_key=k,
                rubric=r, verdicts={'c2': 'met'})
        self.assertTrue(run(self.data))
        self.assertEqual(run(self.data, q={'id': 'q1', 'text': 'changed'}), [])
        self.assertEqual(run(self.data, k={'answer': 'B'}), [])
        self.assertEqual(run(self.data, r={'c2': 'changed'}), [])
        changed = deepcopy(self.data)
        changed['knowledge_components'][0]['observable'] = 'changed without version bump'
        self.assertEqual(run(changed), [])
        self.target['version'] = 'new-source-version'
        self.assertEqual(run(self.data), [])
        self.target['version'] = 'v1'
        record['mapping']['criteria']['c2']['evaluated_kcs'] = ['a']
        self.assertEqual(run(self.data), [])
        self.assertEqual(run(dict(self.data, version='v2')), [])

    def test_prerequisites_reject_dangling_self_and_cycles(self):
        for relations in ([{'from': 'a', 'to': 'missing', 'type': 'prerequisite'}],
                          [{'from': 'a', 'to': 'a', 'type': 'prerequisite'}],
                          [{'from': 'a', 'to': 'b', 'type': 'prerequisite'},
                           {'from': 'b', 'to': 'a', 'type': 'prerequisite'}]):
            with self.subTest(relations=relations), self.assertRaises(ValueError):
                validate_registry(dict(self.data, relations=relations))
        validate_registry(dict(self.data, relations=[{'from': 'a', 'to': 'b', 'type': 'related_to'},
                                                      {'from': 'b', 'to': 'a', 'type': 'related_to'}]))

    def test_candidate_and_missing_reviewer_cannot_grant_coverage(self):
        question, key, rubric, record = self.add_assessment()
        record['status'] = 'candidate'
        registry = self.registry()
        self.assertEqual(registry.evaluated_coverage('assessment-1', question=question, answer_key=key,
                         rubric=rubric, verdicts={'c2': 'met'}), [])
        record.update(status='reviewed', reviewer='')
        with self.assertRaises(ValueError):
            self.registry()


if __name__ == '__main__':
    unittest.main()
