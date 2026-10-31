"""采集适配不能利用金标泄漏，也不能把排版栏框或错误资产当命中。"""
import unittest
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from scripts.build_layer4_benchmark import data_table
from scripts.collect_layer4_baseline import attach_provenance, collect
from scripts.evaluate_layer4_benchmark import matches
from scripts.build_layer4_benchmark import digest
from scripts.diagnose_layer4_baseline import diagnose


class Layer4CollectionTests(unittest.TestCase):
    def test_sidebar_is_not_a_data_table(self):
        self.assertFalse(data_table({'kind': 'table', 'rows': [['拓展阅读']]}))
        self.assertFalse(data_table({'kind': 'table', 'rows': [['长篇说明'*20]]}))
        self.assertTrue(data_table({'kind': 'table', 'rows': [
            ['实验条件及控制要求', '因变量的测量方式'], ['呈现不同强度的刺激', '记录每个被试的反应时，单位为毫秒']]}))

    def test_scope_is_taken_from_question_not_gold(self):
        calls = []
        def retrieve(query, **kwargs):
            calls.append((query, kwargs))
            return []
        sources, trace = collect({'question': '请解释第二章的自变量', 'category': 'definition',
                                  'supports': [{'chapter_id': 99, 'quote': '禁止泄漏的金标'}]}, {}, retrieve)
        self.assertEqual(sources, [])
        self.assertEqual(calls[0][1]['chapter_id'], 2)
        self.assertNotIn('禁止泄漏', calls[0][0])
        self.assertFalse(trace['graph_upgrade_exercised'])

    def test_span_does_not_claim_every_block_in_range(self):
        from agents.q3_navigation import SourceRef
        chunk = SimpleNamespace(text='研究者控制条件', block_start=1, block_end=3)
        original = SourceRef('id', 'doc', chunk.text, version='v')
        with patch('agents.q3_navigation.source_from_chunk', return_value=original):
            source = attach_provenance(chunk, [
                {'block_index': 1, 'kind': 'paragraph', 'text': '未命中的文字'},
                {'block_index': 3, 'kind': 'paragraph', 'text': chunk.text}])
        self.assertEqual([s['block_id'] for s in source.location['source_spans']], [3])

    def test_asset_identity_needs_hash_and_document(self):
        support = {'document_id': 'doc', 'version': 'v', 'asset_id': 'image-01-0001',
                   'asset_sha256': 'hash', 'block_id': 17}
        image = {'id': support['asset_id'], 'sha256': 'hash', 'document_id': 'doc', 'version': 'v'}
        source = {'document_id': 'doc', 'version': 'v', 'image_refs': [image]}
        self.assertTrue(matches(source, support))
        image['sha256'] = 'other'
        self.assertFalse(matches(source, support))
        image.update(sha256='hash', document_id='other')
        self.assertFalse(matches(source, support))

    def test_failure_stage_and_readonly_index_are_preserved(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            index = root/'index.db'
            db = sqlite3.connect(index)
            db.execute('CREATE TABLE chunks(id TEXT,chapter_id INTEGER,block_start INTEGER,block_end INTEGER,text TEXT)')
            db.executemany('INSERT INTO chunks VALUES(?,?,?,?,?)', [('c'+str(i),1,i,i,'原文') for i in (1,2,3)])
            db.commit(); db.close()
            data = root/'data.json'
            data.write_text(json.dumps({'cases': [{'id': 'case', 'supports': [
                {'document_id':'doc','version':'v','chapter_id':1,'block_id':i,'object_id':str(i),'quote':'原文'}
                for i in range(4)]}]}))
            index_hash = digest(index)
            report = {'manifest': {'benchmark_sha256':digest(data),'index_sha256':index_hash}, 'runs': [
                {'case_id':'case','category':'definition','sources':[], 'trace':{'retrieval':{
                    'candidates':['c2','c3'],'selected':['c3']}}}]}
            result = diagnose(data, report, index)
            self.assertEqual(set(result['reasons']), {'not_covered_by_index_block_range','outside_recall_candidates',
                                                     'outside_final_topk_or_gate','selected_range_without_matching_provenance'})
            self.assertEqual(digest(index), index_hash)
            report['manifest']['index_sha256'] = 'wrong'
            with self.assertRaisesRegex(ValueError, 'index_report_mismatch'):
                diagnose(data, report, index)


if __name__ == '__main__':
    unittest.main()
