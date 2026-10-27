"""TA0契约自检：原生尚未启用、入口完整、对象不出现两个活动写入方。"""
import importlib.util
import asyncio
import json
from pathlib import Path
import unittest
from unittest.mock import patch

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

    def test_model_attempt_counter_covers_installed_sync_and_async_clients(self):
        import httpx
        import httpx2
        spec = importlib.util.spec_from_file_location('ta0_baseline_counter', ROOT / 'scripts/check_ta0_baseline.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        async def original_async(client, request, *args, **kwargs):
            return 'ok'
        with patch.object(httpx.Client, 'send', return_value='ok'), \
             patch.object(httpx2.Client, 'send', return_value='ok'), \
             patch.object(httpx2.AsyncClient, 'send', new=original_async):
            with module.count_model_requests() as (counts, carriers):
                httpx.Client.send(None, httpx.Request('POST', 'https://example.invalid/v1/chat/completions'))
                httpx2.Client.send(None, httpx2.Request('POST', 'https://example.invalid/v1/chat/completions'))
                asyncio.run(httpx2.AsyncClient.send(None, httpx2.Request('POST', 'https://example.invalid/v1/embeddings')))
                self.assertEqual(dict(counts), {'model': 2, 'embedding': 1})
                self.assertEqual(carriers, ['httpx', 'httpx2'])


if __name__ == '__main__':
    unittest.main()
