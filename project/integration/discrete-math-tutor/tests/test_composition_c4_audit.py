import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from scripts.audit_composition_c4 import audit
from scripts.benchmark_output_speed import isolated_endpoint
from scripts.prepare_c4_review import prepare


class CompositionAuditTests(unittest.TestCase):
    def test_only_explicit_isolated_local_ports_are_allowed(self):
        self.assertTrue(isolated_endpoint('http://127.0.0.1:8052'))
        for url in ('http://127.0.0.1:8000','http://localhost','https://example.com:8052'):
            self.assertFalse(isolated_endpoint(url))
    def test_audit_separates_missing_citation_failure_and_semantic_review(self):
        with TemporaryDirectory() as tmp:
            path=Path(tmp)
            row={'passed':True,'seconds':4,'events':[{'event':'answer_replace','seconds':3,
                'data':{'answer_id':'a','authoritative':True,'text':'内容[2]'}},
                {'event':'answer_state','seconds':4,'data':{'answer_id':'a','state':'saved','round_id':1}}],
                'result':{'answer_status':'answered','reply':'内容[2]','pdf_references':[{'source_index':0}]}}
            (path/'0-example-after.json').write_text(json.dumps(row),encoding='utf-8')
            report=audit(path);case=report['cases'][0]
            self.assertFalse(case['citation_indices_valid'])
            self.assertEqual(case['effective_first_answer'],3)
            self.assertEqual(case['semantic_review'],'待人工审核')
            self.assertIsNone(report['semantic_passed'])

    def test_blind_review_excludes_variant_and_never_overwrites_annotations(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);raw={'request':{'message':'问题'},'result':{'reply':'回答','answer_status':'answered',
                'pdf_references':[{'source_index':0,'evidence':{'quote':'教材原文'}}]}}
            (root/'0-example-after.json').write_text(json.dumps(raw),encoding='utf-8')
            sheet=root/'sheet.json';key=root/'key.json'
            self.assertEqual(prepare(root,sheet,key),1)
            row=json.loads(sheet.read_text(encoding='utf-8'))['rows'][0]
            self.assertNotIn('after',json.dumps(row,ensure_ascii=False))
            self.assertIsNone(row['source_support'])
            self.assertEqual(row['source_quotes'][0]['quote'],'教材原文')
            original=sheet.read_bytes()
            with self.assertRaises(ValueError):prepare(root,sheet,key)
            self.assertEqual(sheet.read_bytes(),original)
