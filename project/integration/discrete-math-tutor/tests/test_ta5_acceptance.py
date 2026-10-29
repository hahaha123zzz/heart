"""联合验收不能用旧版本、缺失证据或单元全绿冒充发布通过。"""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.check_ta5_acceptance import CASES, summarize, validate_evidence


class TA5AcceptanceTests(unittest.TestCase):
    def report(self):
        return {'source_digest': 'current', 'modules': {m: {'passed': True}
            for _, names, _ in CASES.values() for m in names}}

    def test_all_unit_tests_passed_still_does_not_pass_release(self):
        result = summarize([self.report()], [], 'current')
        self.assertFalse(result['release_ready'])
        self.assertEqual(len(result['cases']), 18)
        self.assertIn('native_unified', result['cases'][16]['missing'])

    def test_old_code_or_conflicting_results_cannot_be_combined(self):
        with self.assertRaises(ValueError):summarize([self.report()], [], 'other')
        other = self.report();other['modules']['test_teaching_modes'] = {'passed': False}
        with self.assertRaises(ValueError):summarize([self.report(), other], [], 'current')

    def test_missing_changed_or_outside_artifact_does_not_count(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder);artifact = root/'proof.json';artifact.write_text('{}', encoding='utf-8')
            record = {'case_id': 'TE12', 'layer': 'browser', 'status': 'passed', 'source_digest': 'current',
                'artifacts': [{'path': 'proof.json', 'sha256': hashlib.sha256(b'{}').hexdigest()}]}
            with patch('scripts.check_ta5_acceptance.ROOT', root):
                self.assertTrue(validate_evidence(record, 'current'))
                self.assertFalse(validate_evidence(record, 'old'))
                artifact.write_text('changed', encoding='utf-8')
                self.assertFalse(validate_evidence(record, 'current'))
                record['artifacts'][0]['path'] = '../outside.json'
                self.assertFalse(validate_evidence(record, 'current'))

    def test_missing_tests_or_incomplete_artifact_cannot_become_green(self):
        report = self.report();report['modules'].pop('test_native_review')
        result = summarize([report], [], 'current')
        self.assertIn('test_native_review', result['cases'][11]['missing'])
        self.assertFalse(validate_evidence({'case_id': 'TE12', 'status': 'passed'}, 'current'))
