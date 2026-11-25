"""LightRAG 启动核验分段：发行/输入核验、PostgreSQL 基线、来源映射逐章。"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from knowledge import startup_trace
from knowledge.lightrag.course_input import COURSE
from knowledge.lightrag.retrieval import LightRagBackend
from knowledge.lightrag.storage import verify_manifest


def rows(folder):
    written = list(Path(folder).glob('*.jsonl'))
    assert len(written) == 1, written
    return {row['stage']: row for row in
            (json.loads(line) for line in written[0].read_text(encoding='utf-8').splitlines())}


class LightRagStartupTraceTests(unittest.TestCase):
    def setUp(self):
        startup_trace.reset()

    tearDown = setUp

    def test_validate_splits_control_input_host_scan_and_control_digest(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'input_manifest.json').write_text(json.dumps(
                {'course_id': COURSE, 'files': {'a': 'b'}, 'source_root': str(root)}), encoding='utf-8')
            (root / 'progress.json').write_text(json.dumps({'state': 'candidate_complete',
                'chapters': {str(i): {'complete': True} for i in range(1, 12)}}), encoding='utf-8')
            (root / 'index_files.json').write_text('{}', encoding='utf-8')
            snapshot = {}
            with (patch.dict(os.environ, STARTUP_ID='lightrag-validate', STARTUP_TRACE_DIR=folder),
                  patch('knowledge.lightrag.retrieval.digest', return_value='sha'),
                  patch('knowledge.lightrag.retrieval.verify'),
                  patch('knowledge.lightrag.retrieval.verify_active', return_value={'extra': 'x'}),
                  patch('knowledge.lightrag.storage.verify_manifest', return_value={'n': {}})):
                LightRagBackend(root, authorized_course_ids={COURSE}, allow_candidate=True,
                                source_root=root).validate(COURSE, snapshot=snapshot)
            recorded = rows(folder)
            for stage in ('lightrag.manifest', 'lightrag.manifest.control_files', 'lightrag.index_manifest',
                          'lightrag.manifest.frozen_input', 'lightrag.manifest.host_textbook',
                          'lightrag.manifest.control_digest'):
                self.assertEqual(recorded[stage]['status'], 'ok', stage)
            self.assertEqual(recorded['lightrag.manifest.control_files']['fields']['chapters'], 11)
            self.assertEqual(recorded['lightrag.manifest.host_textbook']['fields']['files'], 2)
            self.assertEqual(recorded['lightrag.manifest.host_textbook']['fields']['extra_files'], 1)
            self.assertEqual(recorded['lightrag.manifest.control_digest']['fields']['files'], 5)
            self.assertEqual(recorded['lightrag.manifest']['fields']['files'], 1)

    def test_verify_manifest_records_postgres_baseline_before_table_checks(self):
        with TemporaryDirectory() as folder:
            trace = startup_trace.Trace('host', path=Path(folder) / 'host.jsonl', sid='lightrag-pg')
            entry = {'row_count': 2, 'id_sha256': 'x', 'source_signature': 's'}
            with (patch('knowledge.lightrag.storage.read_manifest', return_value={'LIGHTRAG_DOC_FULL': entry}),
                  patch('knowledge.lightrag.storage._workspace', return_value='w'),
                  patch('knowledge.lightrag.storage._pg_connect'),
                  patch('knowledge.lightrag.storage.table_fingerprint',
                        return_value={'row_count': 2, 'id_sha256': 'x'})):
                verify_manifest(Path(folder), source_signature='s', trace=trace,
                                parent='lightrag.index_manifest')
            recorded = rows(folder)
            self.assertEqual(recorded['lightrag.pg.baseline']['parent'], 'lightrag.index_manifest')
            self.assertEqual(recorded['lightrag.pg.baseline']['fields']['namespaces'], 1)
            self.assertEqual(recorded['lightrag.pg.tables']['fields']['tables'], 1)
            self.assertEqual(recorded['lightrag.pg.tables']['fields']['rows'], 2)

    def test_source_map_records_each_chapter_and_the_slowest(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            chapter = root / 'input' / 'chapters' / 'chapter_01'
            chapter.mkdir(parents=True)
            blocks = [{'block_index': 0, 'text': '正文', 'rows': None, 'section_id': 's1',
                       'section': '第一节', 'kind': 'text', 'image_ids': [], 'formula_ids': []}]
            document = chapter / 'document.json'
            document.write_text(json.dumps({'source': 'chapter.docx', 'blocks': blocks}), encoding='utf-8')
            (root / 'input' / 'pdf_manifest.json').write_text(json.dumps(
                [{'chapter_id': 1, 'document_id': 'doc-1', 'version': 'v1'}]), encoding='utf-8')
            (root / 'source_map.json').write_text(json.dumps({'chapter_01.generated.pdf': {
                'chapter_id': 1, 'source': 'chapter.docx', 'document_id': 'doc-1', 'version': 'v1',
                'document_sha256': hashlib.sha256(document.read_bytes()).hexdigest(),
                'blocks': blocks}}), encoding='utf-8')
            with patch.dict(os.environ, STARTUP_ID='lightrag-source-map', STARTUP_TRACE_DIR=folder):
                mapping = LightRagBackend(root, authorized_course_ids={COURSE},
                                          allow_candidate=True).load_source_map()
            recorded = rows(folder)
            self.assertEqual(list(mapping), ['chapter_01.generated.pdf'])
            self.assertEqual(recorded['lightrag.source_map.chapter']['fields']['chapter'], 1)
            self.assertEqual(recorded['lightrag.source_map.chapter']['fields']['blocks'], 1)
            self.assertEqual(recorded['lightrag.source_map']['fields']['chapters'], 1)
            self.assertEqual(recorded['lightrag.source_map']['fields']['slowest_chapter'], 1)


    def test_resident_start_records_sdk_and_per_chapter_provenance(self):
        from unittest.mock import AsyncMock
        from knowledge.fixed_book import ResidentGraph
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'blocks.json').write_text('[{"heart_block_index": 3}]', encoding='utf-8')
            sidecar = root / 'index' / 'tables.json'
            sidecar.parent.mkdir()
            sidecar.write_text(json.dumps({'tables': {'t1': {'self_ref': 'blocks.json#/0'}}}),
                               encoding='utf-8')
            rag = SimpleNamespace(full_docs=SimpleNamespace(get_by_id=AsyncMock(
                return_value={'sidecar_location': str(root / 'index')})))
            graph = ResidentGraph(SimpleNamespace(candidate=root, source_map={
                'chapter_01.generated.pdf': {'chapter_id': 1}}),
                SimpleNamespace(dim=2, max_tokens=32), {})
            with (patch.dict(os.environ, STARTUP_ID='resident-start', STARTUP_TRACE_DIR=folder),
                  patch('knowledge.lightrag.engine.build_rag', return_value=rag),
                  patch('knowledge.lightrag.engine.initialize', new=AsyncMock()),
                  patch('knowledge.lightrag.engine.finalize', new=AsyncMock()),
                  patch('knowledge.lightrag.paths.bind_candidate_sidecars', return_value={}),
                  patch('knowledge.lightrag.ingress.load_verified_bundle',
                        return_value=({'blocks': {'path': 'blocks.json'}}, root)),
                  patch('lightrag.utils_pipeline.sidecar_modality_path',
                        side_effect=lambda location, kind: str(sidecar) if kind == 'tables' else '')):
                asyncio.run(graph.start())
            recorded = rows(folder)
            self.assertEqual(recorded['lightrag.resident.start']['fields']['chapters'], 1)
            self.assertEqual(recorded['lightrag.resident.start']['fields']['slowest_chapter'], 1)
            self.assertEqual(recorded['lightrag.resident.start']['status'], 'ok')
            chapter = recorded['lightrag.provenance.chapter_01']
            self.assertEqual(chapter['parent'], 'lightrag.resident.start')
            self.assertEqual(chapter['fields']['chapter'], 1)
            for child in ('lightrag.provenance.bundle', 'lightrag.provenance.document',
                          'lightrag.provenance.sidecar'):
                self.assertEqual(recorded[child]['parent'], 'lightrag.provenance.chapter_01')
            self.assertEqual(recorded['lightrag.provenance.sidecar']['fields']['modality'], 'tables')
            self.assertEqual(recorded['lightrag.sdk.build']['parent'], 'lightrag.resident.start')


if __name__ == '__main__':
    unittest.main()
