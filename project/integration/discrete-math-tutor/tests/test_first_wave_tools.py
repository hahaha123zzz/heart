"""隔离TW0/TW1，不调用外部模型，不打开正式学生库或教材索引。"""
from contextlib import ExitStack
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agents.q3_tools import build_registry
from agents.tools.first_wave import (ReadBinding, ReadResources, register_sources,
    readonly_tools, MaterialOutlineTool, ReadMaterialTool, ReadSourceTool, ReadMemoryTool, KbFilesTool)
from agents.tools.first_wave_contracts import DEFINITIONS, SCOPES
from agents.tools.first_wave_services import CourseReadService
from agents.tool_protocol import ToolContext, Cancellation, CancelledError


class TextbookResourceFixture(unittest.TestCase):
    def setUp(self):
        import fitz
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'manifest.json').write_text(json.dumps({'chapters': [
            {'id': 1, 'title': '实验方法', 'sections': [{'id': 1, 'title': '变量'}]}]}), encoding='utf-8')
        self.stack = self.enterContext(ExitStack())
        self.stack.enter_context(patch('knowledge.course_config.PSYCHOLOGY_DIR', self.root))
        directory = self.root / 'chapters/chapter_01'
        directory.mkdir(parents=True)
        self.path = directory / 'chapter_01.generated.pdf'
        self.texts = ['Independent variable is manipulated by the researcher.',
                      'Dependent variable is the measured outcome.',
                      'Keep other conditions constant to control confounding.']
        pdf = fitz.open()
        for text in self.texts:
            page = pdf.new_page()
            page.insert_text((50, 70), text)
        pdf.save(self.path)
        pdf.close()
        self.version = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.docid = 'experimental-psychology-3:chapter-01'
        self.record = {'document_id': self.docid, 'course_id': 'experimental-psychology-3',
            'chapter_id': 1, 'version': self.version, 'source': '心理学.txt', 'title': '实验方法',
            'page_count': 3, 'sections': [{'id': 1, 'title': '变量', 'page': 1, 'verified': True}]}
        self.blocks = [{'block_index': i, 'text': text, 'kind': 'paragraph', 'section_id': 1}
                       for i, text in enumerate(self.texts)]
        (directory / 'document.json').write_text(json.dumps({'source': '心理学.txt', 'blocks': self.blocks}), encoding='utf-8')
        from knowledge import pdf_reader, citation_index
        self.unit = {'id': 'ch1:s1:b0', 'title': '变量', 'chapter_id': 1, 'section_id': 1,
            'chapter_title': '实验方法', 'section_title': '变量', 'version': 'unit-v1',
            'page': 1, 'source_valid': True, 'source_block_ids': [0, 1, 2]}
        self.stack.enter_context(patch.object(pdf_reader, 'documents', return_value=[self.record]))
        self.stack.enter_context(patch('knowledge.grounded_citations.documents', return_value=[self.record]))
        self.stack.enter_context(patch.object(pdf_reader, 'PSYCHOLOGY_DIR', self.root))
        self.stack.enter_context(patch.object(citation_index, 'PSYCHOLOGY_DIR', self.root))
        self.stack.enter_context(patch('knowledge.course_navigation.outline', return_value=[self.unit]))
        self.read_target = self.stack.enter_context(patch('knowledge.course_navigation.read_target', return_value=[]))
        self.release = self.stack.enter_context(patch('knowledge.course_release.validate', return_value={'release_id': 'r1'}))
        self.binding = ReadBinding('s', 'session', 'task', 'experimental-psychology-3', 'r1',
                                   ((self.docid, self.version),))
        self.service = CourseReadService()
        self.resources = ReadResources(self.binding, self.service)
        self.context = ToolContext('s', 'session', task_id='task', cancellation=Cancellation(),
                                   state={'first_wave': self.resources})

    def pages(self, **extra):
        return {'document_id': self.docid, 'version': self.version, 'page': 1, **extra}

class TextbookFixture(TextbookResourceFixture):
    def test_late_media_does_not_reserve_first_wave_sources(self):
        import time
        from types import SimpleNamespace
        from agents.q3_tools import RetrieveCourseTool
        from agents.q3_navigation import SourceRef, LearningTarget
        source = self.service.read_material(self.binding, self.pages(), lambda: None)[1][0]
        self.context.navigation = SimpleNamespace(search=lambda **kw: [SourceRef(**source)])
        self.context.state['learning_target'] = LearningTarget('t', '变量')
        self.context.deadline = time.monotonic() + .05
        with patch('knowledge.answer_media.selected_media', side_effect=lambda *a, **kw: (time.sleep(.08) or [])):
            with self.assertRaises(TimeoutError):
                RetrieveCourseTool().run({'query': '变量'}, self.context)
        self.assertFalse(self.resources.source_index)
        self.assertNotIn('source_offset', self.context.state)

    def test_empty_block_does_not_abort_unit_reading(self):
        blocks = [{'block_id': 99, 'text': '', 'section_id': 1},
                  {'block_id': 0, 'text': self.texts[0], 'section_id': 1}]
        value, sources = self.service._blocks(self.record, blocks, lambda: None)
        self.assertEqual([s['text'] for s in sources], [self.texts[0]])

    def test_unmapped_unit_returns_explicit_page_fallback_without_fake_highlight(self):
        from agents.tools.first_wave import ReadFailure
        with patch.object(self.service, '_blocks', side_effect=ReadFailure('unlocated', '脚注不匹配')):
            value, sources = self.service.read_material(self.binding, {'unit_id': self.unit['id']}, lambda: None)
        self.assertFalse(value['unit_read_complete'])
        self.assertEqual(value['range_kind'], 'page_fallback')
        self.assertEqual(sources[0]['location']['evidence']['location_status'], 'page')
        self.assertEqual(sources[0]['location']['evidence']['rects'], [])
        self.service.verify_source(self.binding, sources[0])

    def test_outline_real_metadata_not_text_or_sources(self):
        result = MaterialOutlineTool().run({}, self.context)
        self.assertTrue(result.success, result.content)
        self.assertEqual(result.metadata['data']['items'][0]['id'], self.unit['id'])
        self.assertNotIn('blocks', result.content)
        self.assertEqual(result.sources, [])

    def test_outline_pagination(self):
        rows = [dict(self.unit, id=str(i)) for i in range(3)]
        with patch('knowledge.course_navigation.outline', return_value=rows):
            result = MaterialOutlineTool().run({'limit': 1, 'offset': 1}, self.context)
        self.assertEqual(result.metadata['data']['next_offset'], 2)
        self.assertEqual(result.metadata['data']['items'][0]['id'], '1')

    def test_pages_are_verbatim_versioned_and_bounded(self):
        result = ReadMaterialTool().run(self.pages(end_page=3), self.context)
        self.assertTrue(result.success, result.content)
        self.assertEqual([s['page'] for s in result.sources], [1, 2, 3])
        self.assertIn(self.texts[1], result.metadata['data']['text'])
        self.assertEqual(result.sources[0]['location']['evidence']['location_status'], 'page')
        self.assertEqual([s['index'] for s in result.sources], [1, 2, 3])
        model = json.loads(result.content)
        self.assertIn('[2]', model['text'])
        self.assertEqual(model['citations'][1]['index'], 2)

    def test_unit_uses_existing_service_and_exact_q2_locations(self):
        result = ReadMaterialTool().run({'unit_id': self.unit['id']}, self.context)
        self.assertTrue(result.success, result.content)
        self.read_target.assert_called_once()
        for source in result.sources:
            from knowledge.lightrag.retrieval import as_textbook_chunk
            self.assertEqual(as_textbook_chunk(source).text, source['text'])
            evidence = source['location']['evidence']
            self.assertEqual(evidence['location_status'], 'exact')
            self.assertTrue(evidence['rects'])
            self.assertEqual(evidence['quote'], source['text'])

    def test_expansion_uses_live_ledger_no_search_and_dedupes(self):
        result = ReadMaterialTool().run({'unit_id': self.unit['id'], 'block_offset': 1}, self.context)
        source = result.sources[0]
        exact = ReadSourceTool().run({'source_id': source['source_id']}, self.context)
        self.assertEqual(exact.sources[0]['index'], source['index'])
        expanded = ReadSourceTool().run({'source_id': source['source_id'], 'expand': True}, self.context)
        self.assertTrue(expanded.success, expanded.content)
        self.assertEqual([s['index'] for s in expanded.sources], [3, 1, 2])
        self.assertEqual(len(self.resources.source_index), 3)

    def test_retrieval_hook_joins_same_ledger(self):
        result = ReadMaterialTool().run(self.pages(), self.context)
        source = result.sources[0]
        self.assertEqual(register_sources(self.context, [source])[0]['index'], 1)
        self.assertEqual(self.context.state['source_offset'], 1)

    def test_forged_evidence_is_not_upgraded(self):
        from agents.tools.first_wave import ReadFailure
        source = self.service.read_material(self.binding, {'unit_id': self.unit['id']}, lambda: None)[1][0]
        source['text'] = 'Not in the textbook.'
        source['location']['evidence']['quote'] = source['text']
        with self.assertRaises(ReadFailure):
            register_sources(self.context, [source])
        self.assertEqual(self.resources.source_index, {})

    def test_registration_uses_same_bound_index_as_selected_evidence(self):
        from unittest.mock import Mock
        from agents.tools.first_wave import ReadFailure
        text='重复出现的教材短句'
        rectangles=[{'page':1,'x1':.1,'y1':.1,'x2':.5,'y2':.2}]
        source={'document_id':self.docid,'version':self.version,'section_id':1,'text':text,
                'location':{'evidence':{'source_block_id':7,'block_start':0,'block_end':len(text),
                                        'location_status':'exact','rects':rectangles}}}
        index=Mock()
        index.blocks.return_value=[{'text':text,'section_id':1}]
        index.locate.return_value={'status':'exact','rects':rectangles}
        index.document.return_value={'text':text}
        with patch('knowledge.grounded_citations.settings',return_value=Path('bound-index.sqlite3')), \
             patch('knowledge.citation_index.CitationIndex',return_value=index), \
             patch('knowledge.citation_index.LiveCitationIndex',side_effect=AssertionError('不能重新用全文猜位置')):
            self.service.verify_source(self.binding,source)
            source['location']['evidence']['rects']=[{'page':3}]
            with self.assertRaises(ReadFailure):self.service.verify_source(self.binding,source)
            source['location']['evidence'].update(location_status='section',rects=[])
            self.service.verify_source(self.binding,source)

    def test_unknown_source_fails_closed(self):
        result = ReadSourceTool().run({'source_id': 'history-or-other-task'}, self.context)
        self.assertEqual(result.metadata['error'], 'unknown_source')

    def test_user_task_and_session_mismatch(self):
        for key, value in [('student_id', 'other'), ('task_id', 'old'), ('session_id', 'old')]:
            with self.subTest(key=key):
                ctx = replace(self.context, **{key: value})
                self.assertEqual(MaterialOutlineTool().run({}, ctx).metadata['error'], 'binding_mismatch')

    def test_stale_release_does_not_return_sources(self):
        self.release.side_effect = ValueError('changed')
        result = ReadMaterialTool().run(self.pages(), self.context)
        self.assertFalse(result.success)
        self.assertFalse(self.resources.source_index)

    def test_changed_pdf_fails_closed(self):
        self.path.write_bytes(b'changed')
        self.assertFalse(ReadMaterialTool().run(self.pages(), self.context).success)

    def test_cancellation_before_and_during_read(self):
        self.context.cancellation.cancel()
        with self.assertRaises(CancelledError):
            ReadMaterialTool().run(self.pages(), self.context)
        self.context.cancellation = Cancellation()
        with patch.object(self.service, 'read_material', side_effect=lambda *a: (
            self.context.cancellation.cancel(), ({'text': ''}, []))[1]):
            with self.assertRaises(CancelledError):
                ReadMaterialTool().run(self.pages(), self.context)
        self.assertFalse(self.resources.source_index)

    def test_budget_registration_is_atomic(self):
        result = ReadMaterialTool().run(self.pages(), self.context)
        self.context.state['source_offset'] = 24
        rows = self.service.read_material(self.binding, self.pages(page=2), lambda: None)[1]
        from agents.tools.first_wave import ReadFailure
        with self.assertRaises(ReadFailure):
            register_sources(self.context, rows)
        self.assertEqual(len(self.resources.source_index), 1)
        self.assertEqual(result.sources[0]['index'], 1)

    def test_invalid_arguments_closed_schema_and_locator(self):
        bad = [{}, {'unit_id': self.unit['id'], 'page': 1}, self.pages(end_page=4),
               self.pages(page=0), self.pages(version='old'), self.pages(document_id='../secret'),
               self.pages(student_id='other'), self.pages(_source_index='spoof'),
               self.pages(page=True), self.pages(page=None), self.pages(block_offset=1)]
        for args in bad:
            with self.subTest(args=args):
                self.assertFalse(ReadMaterialTool().run(args, self.context).success)
        self.assertFalse(MaterialOutlineTool().run({'limit': 51}, self.context).success)

    def test_catalog_counts_public_manifest_only(self):
        value = KbFilesTool().run({'pattern': '*实验*'}, self.context).metadata['data']
        self.assertEqual((value['total'], value['matched'], value['listed'], value['omitted']), (1, 1, 1, 0))
        self.assertNotIn('source_sha256', str(value))
        self.assertNotIn(str(self.root), str(value))

    def test_scopes_visible_schemas_and_missing_resources(self):
        tools = readonly_tools(self.resources)
        registry = build_registry(extra_tools=tools, extra_scopes=('course:read',), allow_skills=False)
        self.assertIn('read_material', registry.names())
        self.assertNotIn('read_source', registry.names())
        self.assertNotIn('reader_goto', registry.names())
        for schema in registry.schemas():
            if schema['function']['name'] in DEFINITIONS:
                self.assertIs(schema['function']['parameters']['additionalProperties'], False)
        self.assertEqual(readonly_tools(ReadResources(self.binding)), ())
        ctx = replace(self.context, state={})
        self.assertEqual(MaterialOutlineTool().run({}, ctx).metadata['error'], 'unavailable')

    def test_dispatch_uses_existing_authorization_and_does_not_change_learning(self):
        from agents.tool_dispatch import dispatch_tool_calls
        self.context.state['learning_cursor'] = {'unit_id': 'old', 'understood': False}
        registry = build_registry(extra_tools=readonly_tools(self.resources),
            extra_scopes=('course:read', 'sources:read'), allow_skills=False)
        result = dispatch_tool_calls(tool_calls=[{'id': 'call1', 'name': 'read_material',
            'arguments': self.pages()}], registry=registry, context=self.context)
        self.assertTrue(result.results[0].success)
        self.assertEqual(result.tool_messages[0]['tool_call_id'], 'call1')
        self.assertEqual(self.context.state['learning_cursor'], {'unit_id': 'old', 'understood': False})

    def test_truncation_has_executable_continuation(self):
        with patch('agents.tools.first_wave_services.TEXT_LIMIT', 70):
            first = ReadMaterialTool().run({'unit_id': self.unit['id']}, self.context)
            self.assertTrue(first.success, first.content)
            continuation = first.metadata['data']['continuation']
            self.assertTrue(continuation)
            second = ReadMaterialTool().run(continuation, self.context)
            self.assertTrue(second.success, second.content)
            self.assertNotEqual(first.sources[0]['source_id'], second.sources[0]['source_id'])


class BaselineRegistryTests(unittest.TestCase):
    def test_existing_normal_q5_and_interjection_authorization(self):
        from agents.q5_learning import LearningScope
        from agents.q5_tools import q5_tool_instances
        normal = build_registry(allow_skills=False)
        self.assertEqual(set(normal.names()), {'retrieve_course', 'ask_user', 'lookup_figures'})
        tools = q5_tool_instances(None, LearningScope('s', 'session', 'course'))
        scopes = {s for tool in tools for s in tool.scopes}
        registry = build_registry(extra_tools=tools, extra_scopes=scopes, allow_skills=False)
        self.assertEqual(len(registry.names()), 12)
        insert = [t for t in tools if t.definition.name in ('mastery_status', 'mastery_paths')]
        restricted = build_registry(extra_tools=insert, extra_scopes=('learning:read',), allow_skills=False)
        self.assertEqual(set(restricted.names()), {'retrieve_course', 'ask_user', 'lookup_figures',
                                                    'mastery_status', 'mastery_paths'})
        self.assertFalse(any('write' in scope for tool in readonly_tools(
            ReadResources(ReadBinding('s', 'session', 'task', 'course', 'r', ()), CourseReadService()))
            for scope in tool.scopes))


class MemoryReadTests(unittest.TestCase):
    def test_existing_profile_confirmation_delete_and_zero_writes(self):
        from sqlalchemy import create_engine, event
        from sqlalchemy.orm import sessionmaker
        from database import database as db
        from database.models import Base, Student, LearnerProfileRow, MemoryChangeRow
        from memory.memory_manager import MemoryManager
        from memory.readonly_context import ReadonlyMemoryContext
        with tempfile.TemporaryDirectory() as root:
            engine = create_engine('sqlite:///' + str(Path(root) / 'isolated.db'))
            try:
                Base.metadata.create_all(engine)
                with patch.object(db, 'SessionLocal', sessionmaker(bind=engine)):
                    with db.session_scope() as s:
                        s.add_all([Student(student_id='s', account_type='test'), Student(student_id='other', account_type='test')])
                        s.flush()
                        s.add_all([LearnerProfileRow(student_id='s', preferences={'answer_length': .2, 'example_density': .9}),
                            LearnerProfileRow(student_id='other', preferences={'answer_length': .9}),
                            MemoryChangeRow(student_id='s', action='set_preference', item_key='answer_length', confirmed_value=.2)])
                    statements = []
                    event.listen(engine, 'before_cursor_execute', lambda conn, cursor, sql, *rest: statements.append(sql))
                    binding = ReadBinding('s', 'session', 'task', 'course', 'r', ())
                    resource = ReadResources(binding, memory=ReadonlyMemoryContext(MemoryManager()))
                    ctx = ToolContext('s', 'session', task_id='task', state={'first_wave': resource})
                    result = ReadMemoryTool().run({}, ctx)
                    self.assertTrue(result.success, result.content)
                    self.assertEqual(result.metadata['data']['known'], {'answer_length': .2})
                    self.assertEqual(result.sources, [])
                    self.assertEqual(ReadMemoryTool().run({'section': 'profile'}, ctx).metadata['data']['known'], {})
                    self.assertTrue(all(sql.lstrip().upper().startswith('SELECT') for sql in statements), statements)
                    self.assertFalse(ReadMemoryTool().run({'student_id': 'other'}, ctx).success)
                    self.assertFalse(ReadMemoryTool().run({'section': 'recent'}, ctx).success)
                    with db.session_scope() as s:
                        s.get(LearnerProfileRow, 's').preferences = {}
                    self.assertEqual(ReadMemoryTool().run({}, ctx).metadata['data']['known'], {})
            finally:
                engine.dispose()


if __name__ == '__main__':
    unittest.main()
