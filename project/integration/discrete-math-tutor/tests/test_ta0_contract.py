"""TA0契约自检：原生尚未启用、入口完整、对象不出现两个活动写入方。"""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT.parents[1] / 'docs/research/2026-10-19-deeptutor-conversation-flow'


class TA0ContractTests(unittest.TestCase):
    def test_entry_inventory_and_writer_ownership_are_complete(self):
        contract = json.loads((DOCS / 'TA0_STATE_OWNERSHIP.json').read_text(encoding='utf-8'))
        self.assertFalse(contract['native_cutover_allowed'])
        self.assertEqual({row['id'] for row in contract['entries']}, {'chat', 'learning', 'selection', 'practice', 'ask_user'})
        owners = set(contract['owners'])
        for name, row in contract['objects'].items():
            for phase in ('current', 'after_cutover'):
                with self.subTest(name=name, phase=phase):
                    self.assertIsInstance(row[phase], str)
                    self.assertIn(row[phase], owners)
            self.assertNotIn(row['current'], ('native_turn', 'native_learning'))
        for row in contract['entries']:
            self.assertTrue(set(row['state_objects']) <= set(contract['objects']))
        for name in ('formal_question_interaction', 'formal_mastery_evidence', 'formal_review_state'):
            self.assertEqual(contract['objects'][name]['current'], 'none')
        self.assertEqual(contract['objects']['textbook_navigation']['after_cutover'], 'q2')

    def test_audit_script_has_no_application_import_or_live_call_on_import(self):
        spec = importlib.util.spec_from_file_location('ta0_baseline_check', ROOT / 'scripts/check_ta0_baseline.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(all((ROOT / name).is_file() for name in module.CORE))
        self.assertEqual(module.ROOT, ROOT)
        self.assertTrue(callable(module.audit))


if __name__ == '__main__':
    unittest.main()
