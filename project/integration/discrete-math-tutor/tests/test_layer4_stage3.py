"""覆盖原件篡改、版本串用和缺侧证据；不把命中或原始OMML当语义通过。"""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from agents.q3_navigation import SourceRef
from agents.tools.evidence_requirements import execute_requirements
from knowledge.evidence_objects import ObjectReadRequest, read_object
from scripts.parse_converted_textbook import NS, paragraph_text
from tests.test_evidence_execution import request
from scripts.collect_layer4_stage3 import collect


class ObjectReadTests(unittest.TestCase):
    def setUp(self):
        # 先初始化业务模块，再替换夹具路径，避免首次导入课程目录误读精简测试清单。
        import knowledge.pdf_reader
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root/'chapters/chapter_01'
        self.folder.mkdir(parents=True)
        xml = (f'<w:document xmlns:w="{NS["w"]}" xmlns:m="{NS["m"]}"><w:body>'
               '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>条件</w:t></w:r></w:p></w:tc>'
               '<w:tc><w:p><w:r><w:t>结果</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
               '<w:p><m:oMath><m:r><m:t>x</m:t></m:r></m:oMath></w:p></w:body></w:document>')
        docx = self.folder/'source.docx'
        with ZipFile(docx, 'w') as archive:
            archive.writestr('word/document.xml', xml)
        self.original_hash = hashlib.sha256(docx.read_bytes()).hexdigest()
        self.doc_id = 'experimental-psychology-3:chapter-01'
        raw = list(ET.fromstring(xml).find('w:body', NS))
        self.doc = {'chapter_id': 1, 'docx_sha256': self.original_hash, 'blocks': [
            {'block_index': 0, 'kind': 'table', 'text': '条件\n结果', 'rows': [['条件', '结果']], 'section_id': 1},
            {'block_index': 1, 'kind': 'paragraph', 'text': paragraph_text(raw[1]), 'section_id': 1}],
            'omml_objects': [{'id': self.doc_id+':omml-001', 'block_index': 1, 'path': 'formula.xml'}]}
        (self.folder/'formula.xml').write_bytes(ET.tostring(raw[1].find('.//m:oMath', NS), encoding='utf-8'))
        (self.root/'manifest.json').write_text(json.dumps({'full_import': {'chapters': [
            {'chapter_id': 1, 'docx': 'chapters/chapter_01/source.docx', 'source_sha256': self.original_hash}]}}))
        self.pdf = self.folder/'reader.pdf'
        self.pdf.write_bytes(b'fixture pdf version bytes')
        self.version = hashlib.sha256(self.pdf.read_bytes()).hexdigest()
        self.record = {'document_id': self.doc_id, 'version': self.version, 'chapter_id': 1}
        for target, kwargs in (
                ('knowledge.course_config.PSYCHOLOGY_DIR', {'new': self.root}),
                ('knowledge.pdf_reader.document', {'return_value': self.record}),
                ('knowledge.pdf_reader.pdf_path', {'return_value': self.pdf}),
                ('knowledge.citation_index.LiveCitationIndex', {})):
            mock = patch(target, **kwargs)
            value = mock.start()
            self.addCleanup(mock.stop)
            if target.endswith('LiveCitationIndex'):
                value.return_value.locate.return_value = {'status': 'unlocated', 'rects': []}

    def read(self, kind='table', *, version=None):
        (self.folder/'document.json').write_text(json.dumps(self.doc), encoding='utf-8')
        return read_object(ObjectReadRequest(document_id=self.doc_id, version=version or self.version,
            object_id=self.doc_id+(':b0' if kind == 'table' else ':omml-001'), kind=kind))

    def test_table_rows_and_original_provenance_without_fake_page(self):
        result = self.read()
        self.assertEqual(result['payload']['rows'], [['条件', '结果']])
        self.assertEqual(len(result['sources']), 2)
        self.assertTrue(all(s.page is None and not s.location['rects'] for s in result['sources']))
        self.assertEqual(result['sources'][0].location['source_spans'][0]['block_id'], 0)
        self.assertFalse(result['semantic_verified'])

    def test_raw_formula_does_not_claim_verified_latex_or_pixels(self):
        result = self.read('formula')
        self.assertIn('oMath', result['payload']['raw_omml'])
        self.assertNotIn('latex', result['payload'])
        self.assertFalse(result['model_saw_pixels'])
        self.assertFalse(result['payload']['semantic_verified'])

    def test_old_pdf_and_changed_original_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'stale_document'):
            self.read(version='0'*64)
        (self.folder/'source.docx').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'stale_original'):
            self.read()

    def test_forged_rows_and_formula_are_rejected(self):
        self.doc['blocks'][0]['rows'] = [['伪造数据']]
        with self.assertRaisesRegex(ValueError, 'original_table'):
            self.read()
        self.doc['blocks'][0]['rows'] = [['条件', '结果']]
        (self.folder/'formula.xml').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'original_formula'):
            self.read('formula')

    def test_formula_cannot_escape_chapter(self):
        self.doc['omml_objects'][0]['path'] = '../../outside.xml'
        with self.assertRaisesRegex(ValueError, 'outside_chapter'):
            self.read('formula')

    def test_formula_identity_cannot_be_renamed(self):
        self.doc['omml_objects'][0]['id'] = self.doc_id+':omml-002'
        (self.folder/'document.json').write_text(json.dumps(self.doc), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'original_formula'):
            read_object(ObjectReadRequest(document_id=self.doc_id, version=self.version,
                object_id=self.doc_id+':omml-002', kind='formula'))


class RequirementTests(unittest.TestCase):
    def test_score_is_not_support_and_missing_side_blocks_composition(self):
        source = SourceRef('s', 'doc', '第一侧原文', version='version')
        calls = []
        def retrieve(need):
            calls.append(need.id)
            return [source]
        result = execute_requirements(request(), retrieve=retrieve,
            verify_support=lambda need, source: need.id == 'iv')
        self.assertEqual(calls, ['iv', 'dv', 'figure'])
        self.assertEqual(result.missing_required, ['dv'])
        self.assertFalse(result.ready_for_composition)

    def test_optional_missing_and_failure_receipt(self):
        def retrieve(need):
            if need.id == 'figure':
                raise OSError('fixture unavailable')
            return [SourceRef(need.id, 'doc', '核验原文', version='version')]
        result = execute_requirements(request(), retrieve=retrieve, verify_support=lambda *_: True)
        self.assertTrue(result.ready_for_composition)
        self.assertEqual(result.coverage[-1].status, 'unavailable')
        self.assertEqual(result.tool_receipts[-1].status, 'failed')

    def test_cross_version_rejected_before_semantic_check(self):
        verified = []
        result = execute_requirements(request(),
            retrieve=lambda _: [SourceRef('s', 'doc', '原文', version='old')],
            verify_support=lambda *args: verified.append(args) or True)
        self.assertEqual(verified, [])
        self.assertEqual(result.status, 'insufficient')

    def test_cancellation_does_not_return_completed_package(self):
        def cancelled():
            raise RuntimeError('cancelled')
        with self.assertRaisesRegex(RuntimeError, 'cancelled'):
            execute_requirements(request(), retrieve=lambda _: [], verify_support=lambda *_: True,
                                 check_cancelled=cancelled)

    def test_target_and_pixel_scope_are_checked_before_support(self):
        from agents.q3_navigation import LearningTarget
        req = request()
        req.requirements[0].target = LearningTarget('ch2', '第二章', chapter_id=2)
        req.requirements[1].kind = 'image'
        req.requirements[1].pixels_required = True
        req.requirements[2].required = True
        seen = []
        result = execute_requirements(req,
            retrieve=lambda _: [SourceRef('s', 'doc', '原文', version='version', chapter_id=1)],
            verify_support=lambda need, _: seen.append(need.id) or True)
        self.assertEqual(seen, ['figure'])
        self.assertEqual(result.missing_required, ['iv', 'dv'])
        self.assertFalse(result.ready_for_composition)

    def test_split_queries_use_question_only_not_gold(self):
        calls = []
        sources, trace = collect({'category': 'comparison', 'question': '第2章“自变量…”与“因变量…”',
                                 'supports': [{'quote': '禁止泄漏'}]}, {},
                                 lambda q, **kwargs: calls.append((q, kwargs)) or [])
        self.assertEqual([q for q, _ in calls], ['自变量', '因变量'])
        self.assertTrue(all(kw['limit'] == 3 and kw['chapter_id'] == 2 for _, kw in calls))
        self.assertFalse(trace['semantic_verified'])


if __name__ == '__main__':
    unittest.main()
