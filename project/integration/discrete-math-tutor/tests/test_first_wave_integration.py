"""TW2/TW3 隔离接线检查；模型为协议替身，原文/坐标/SQL服务实际执行。"""
from types import SimpleNamespace
from unittest.mock import patch
from tests.test_first_wave_tools import TextbookResourceFixture
from agents.agent_loop import LocalAgentLoop, LoopRequest
from agents.q3_tools import build_registry, RetrieveCourseTool
from agents.tools.first_wave import readonly_tools, restore_sources
from agents.tools.first_wave_runtime import ReaderGotoTool, structured_gate, purpose


class ScriptedLLM:
    def __init__(self, rounds):
        self.rounds = list(rounds)
        self.schemas = []

    def chat_with_tools(self, messages, tools, **kwargs):
        self.schemas.append(tools)
        return self.rounds.pop(0)


def call(name, args):
    import json
    from llm.client import ChatToolResult, ChatToolCall
    return ChatToolResult(text='', finish_reason='tool_calls', tool_calls=[ChatToolCall('call-' + name, name, args, json.dumps(args))])


def answer(text='模型不能替代服务端状态'):
    from llm.client import ChatToolResult
    return ChatToolResult(text=text, finish_reason='stop', tool_calls=[])


class FirstWaveIntegration(TextbookResourceFixture):
    def test_teaching_readiness_still_waits_for_required_memory(self):
        self.resources.memory = SimpleNamespace(read=lambda *args: {'section': 'preferences',
            'known': {}, 'missing': ['answer_length'], 'source_kind': 'explicit_user'})
        client = ScriptedLLM([call('read_memory', {}), answer('按当前问题继续讲解')])
        tools = readonly_tools(self.resources)
        registry = build_registry(extra_tools=tools, extra_scopes={s for t in tools for s in t.scopes}, allow_skills=False)
        result = LocalAgentLoop(client).run(LoopRequest('s', 'session', 'task', 'request', '按我的偏好解释',
            '使用真实偏好', registry, tool_state={'first_wave': self.resources},
            required_tools=('read_memory',), answer_ready=lambda result: True,
            publish_gate=lambda *args: (True, '')))
        self.assertTrue(result.completed, result.error)
        self.assertTrue(client.schemas[0])
        self.assertFalse(client.schemas[1])

    def test_structured_read_bypasses_teaching_and_prefetch_without_progress(self):
        from agents.agent_loop_service import run_agent_loop_turn
        from agents.q3_navigation import StubLearningNavigator, LearningTarget
        from tests.test_q3_q4_integration import FakeMemory
        from models.task_context import TaskContext
        from models.chat_request import ChatRequest
        client = ScriptedLLM([call('material_outline', {})])
        request = ChatRequest(student_id='s', session_id='session', task_id='task', task_revision=1, request_id='request', message='第一章有哪些小节？')
        context = TaskContext(student_id='s', message=request.message, knowledge_point='变量')
        with patch.dict('os.environ', {'ADAPTIVE_TUTORING_ENABLED': '1'}), \
             patch('agents.tools.first_wave_runtime.bind_resources', return_value=(self.resources, readonly_tools(self.resources))), \
             patch('agents.adaptive_tutoring.TeachingTurn') as teaching:
            result = run_agent_loop_turn(orchestrator=SimpleNamespace(llm=client, memory=FakeMemory(), quality_checker=None),
                request=request, context=context, navigator=StubLearningNavigator(target=LearningTarget('t', '变量')))
        teaching.assert_not_called()
        self.assertEqual(result['answer_status'], 'answered')
        self.assertFalse(result['step_advanced'])
        self.assertTrue(result['learning_interjection'])
        self.assertEqual(len(client.schemas), 1)

    def run_loop(self, rounds, *, kind='textbook', required=(), gate=None, previous=None):
        tools = (*readonly_tools(self.resources), ReaderGotoTool(2))
        registry = build_registry(extra_tools=tools,
            extra_scopes={s for t in tools for s in t.scopes}, allow_skills=False)
        self.llm = ScriptedLLM(rounds)
        return LocalAgentLoop(self.llm).run(LoopRequest('s', 'session', 'task', 'request', '问题',
            '只用工具结果', registry, tool_state={'first_wave': self.resources},
            required_tools=required, requires_evidence=kind == 'textbook',
            structured_response=kind != 'textbook',
            publish_gate=gate), resume_state=previous, answer='继续')

    def test_status_gate_uses_tool_facts_not_model_claims(self):
        result = self.run_loop([call('material_outline', {}), answer('你已经全部学会了，教材只有一页。')],
            kind='outline', required=('material_outline',), gate=structured_gate('outline'))
        self.assertTrue(result.completed, result.error)
        self.assertIn('变量', result._publication['reply'])
        self.assertNotIn('全部学会', result._publication['reply'])
        self.assertFalse(result.sources)
        self.assertEqual(len(self.llm.schemas), 1)

    def test_mixed_query_does_not_skip_textbook_evidence_after_memory(self):
        self.resources.memory = SimpleNamespace(read=lambda *args: {'section': 'preferences',
            'known': {'answer_length': .2}, 'missing': [], 'source_kind': 'explicit_user'})
        result = self.run_loop([call('read_memory', {}), call('read_material', self.pages()), answer('教材内容[1]')],
            required=('read_memory',))
        self.assertTrue(result.completed, result.error)
        self.assertTrue(self.llm.schemas[1])
        self.assertFalse(self.llm.schemas[2])
        self.assertEqual(len(result.sources), 1)

    def test_retrieval_then_exact_read_uses_same_number(self):
        source = self.service.read_material(self.binding, {'unit_id': self.unit['id']}, lambda: None)[1][0]
        source['source_id'] = 'q2-selected-evidence'
        source['location']['evidence']['evidence_id'] = source['source_id']
        source['location']['evidence'].pop('page')
        from agents.q3_navigation import SourceRef, LearningTarget
        self.context.state['learning_target'] = LearningTarget(self.unit['id'], '变量')
        self.context.navigation = SimpleNamespace(search=lambda **kw: [SourceRef(**source)], calls=[])
        with patch('knowledge.answer_media.selected_media', return_value=[]), patch('agents.course_search.association_context', return_value=[]):
            first = RetrieveCourseTool().run({'query': '变量'}, self.context)
        self.assertTrue(first.success, first.content)
        from agents.tools.first_wave import ReadMaterialTool
        again = ReadMaterialTool().run({'unit_id': self.unit['id']}, self.context)
        self.assertEqual(first.sources[0]['index'], again.sources[0]['index'])
        self.assertEqual(again.metadata['data']['citation_ids'][0], source['source_id'])

    def test_resume_revalidates_and_preserves_gapped_numbers(self):
        from agents.tools.first_wave import ReadMaterialTool
        result = ReadMaterialTool().run(self.pages(), self.context)
        result.sources[0]['index'] = 4
        self.resources.source_index = {}
        restore_sources(self.context, result.sources)
        self.assertEqual(next(iter(self.resources.source_index.values()))['index'], 4)
        self.assertEqual(self.context.state['source_offset'], 4)

    def test_explicit_attachment_is_reverified_with_new_turn_number(self):
        source = self.service.read_material(self.binding, self.pages(), lambda: None)[1][0]
        source['index'] = 9
        self.resources.attached_sources = [source]
        result = self.run_loop([call('reader_goto', {'source_id': source['source_id']})],
            kind='reader_action', required=('reader_goto',), gate=structured_gate('reader_action'))
        self.assertTrue(result.completed, result.error)
        self.assertEqual(result.sources[0]['index'], 1)
        self.assertEqual(source['index'], 9)

    def test_reader_goto_requests_not_applied_and_quote_failure_no_highlight(self):
        tool = ReaderGotoTool(2)
        a = tool.run(self.pages(quote='不存在的引句'), self.context)
        self.assertTrue(a.success, a.content)
        value = a.metadata['data']['action']
        self.assertEqual(value['status'], 'requested')
        self.assertEqual(value['rects'], [])
        b = tool.run(self.pages(quote='不存在的引句'), self.context)
        self.assertEqual(value['action_id'], b.metadata['data']['action']['action_id'])
        found = tool.run(self.pages(quote=self.texts[0]), self.context)
        self.assertTrue(found.metadata['data']['action']['rects'])
        self.assertFalse(tool.run(self.pages(page=4), self.context).success)

    def test_multi_page_publication_does_not_collapse_distinct_pages(self):
        from knowledge.grounded_citations import EvidenceBundle
        from agents.tools.first_wave import ReadMaterialTool
        from knowledge.lightrag.retrieval import as_textbook_chunk
        result = ReadMaterialTool().run(self.pages(end_page=2), self.context)
        bundle = EvidenceBundle([as_textbook_chunk(s) for s in result.sources],
            [s['location']['evidence'] for s in result.sources], [])
        body, sources, references = bundle.publish('第一页[1]，第二页[2]')
        self.assertEqual(len(references), 2)
        self.assertEqual([r['evidence']['page'] for r in references], [1, 2])

    def test_publish_gate_maps_gapped_global_numbers_to_evidence_positions(self):
        from agents.agent_loop_service import _publish_gate
        from agents.agent_loop import LoopResult
        source = self.service.read_material(self.binding, self.pages(), lambda: None)[1][0]
        source['index'] = 4
        result = LoopResult(sources=[source])
        gate = _publish_gate(SimpleNamespace(memory=None, quality_checker=None),
            SimpleNamespace(message='读取原文'), SimpleNamespace(name='变量'))
        ok, reason = gate('第一页内容[4]', result)
        self.assertTrue(ok, reason)
        self.assertEqual(result._publication['reply'], '第一页内容[1]')

    def test_mixed_purpose_cannot_bypass_fact_gate(self):
        self.assertEqual(purpose('按我的偏好解释自变量'), 'textbook')
        self.assertEqual(purpose('我的偏好是什么'), 'personal_state')
        self.assertEqual(purpose('我的讲解偏好是什么？'), 'personal_state')
        self.assertEqual(purpose('按我的讲解偏好解释自变量'), 'textbook')
        self.assertEqual(purpose('教材有几个文档'), 'catalog')

    def test_course_skill_manifest_and_execution_share_allowlist(self):
        from agents.tools.first_wave_runtime import skill_catalog
        from agents.tools.skill_tools import ReadSkillTool
        from dataclasses import replace
        root = self.root / 'skills'
        for name in ('reasoning-diagrams', 'experimental-design', 'finite-structures'):
            directory = root / name
            directory.mkdir(parents=True)
            (directory / 'SKILL.md').write_text('# 技能\n使用步骤讲解。', encoding='utf-8')
        catalog = skill_catalog(root, 'experimental-psychology-3')
        self.assertIn('experimental-design', catalog)
        self.assertNotIn('finite-structures', catalog)
        ctx = replace(self.context, state={'skills_root': str(root),
            'allowed_skills': ('reasoning-diagrams', 'experimental-design')})
        self.assertFalse(ReadSkillTool().run({'name': 'finite-structures'}, ctx).success)
        self.assertTrue(ReadSkillTool().run({'name': 'experimental-design'}, ctx).success)

    def test_public_entry_mounts_and_publishes_outline(self):
        from agents.agent_loop_service import run_agent_loop_turn
        from agents.q3_navigation import LearningTarget, StubLearningNavigator
        from models.chat_request import ChatRequest
        from models.task_context import TaskContext
        request = ChatRequest(student_id='s', session_id='session', task_id='task', task_revision=2,
                              request_id='request', message='第一章有哪些小节')
        context = TaskContext(student_id='s', session_id='session', message=request.message, knowledge_point='变量')
        tools = (*readonly_tools(self.resources), ReaderGotoTool(2))
        llm = ScriptedLLM([call('material_outline', {}), answer()])
        with patch('agents.tools.first_wave_runtime.bind_resources', return_value=(self.resources, tools)):
            result = run_agent_loop_turn(orchestrator=SimpleNamespace(llm=llm, memory=None), request=request,
                context=context, navigator=StubLearningNavigator(target=LearningTarget('current', '变量')))
        self.assertEqual(result['answer_status'], 'answered', result)
        self.assertTrue(result['learning_interjection'])
        self.assertEqual(result['publication_kind'], 'outline')
        self.assertFalse(result['pdf_references'])


class ReaderReceiptTests(TextbookResourceFixture):
    def setUp(self):
        super().setUp()
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from database import database as db
        from database.models import Base, Student, LearningTaskRow, TaskRequestRow
        from database.learning_tasks import now
        from datetime import timedelta
        self.engine = create_engine('sqlite:///' + str(self.root / 'receipt.db'))
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.enterContext(patch.object(db, 'SessionLocal', sessionmaker(bind=self.engine)))
        self.action = ReaderGotoTool(2).run(self.pages(page=2), self.context).metadata['data']['action']
        with db.session_scope() as session:
            session.add(Student(student_id='s', account_type='test'))
            session.flush()
            result = {'answer_status': 'answered', 'reader_actions': [self.action]}
            session.add(LearningTaskRow(id='task', student_id='s', session_id='session', status='completed',
                revision=3, epoch=0, knowledge_point='变量', result=result, expires_at=now()+timedelta(minutes=20)))
            session.flush()
            session.add(TaskRequestRow(id='receipt', student_id='s', session_id='session', request_id='request',
                task_id='task', payload_hash='hash', result=result))
        self.memory_repo = SimpleNamespace(memory_epoch=lambda *a: 0)

    def receipt(self, **kwargs):
        from agents.reader_actions import ReaderActionReceipt
        return ReaderActionReceipt(**dict(student_id='s', session_id='session', task_revision=3,
            action_id=self.action['action_id'], status='applied', document_id=self.docid,
            version=self.version, page=2) | kwargs)

    def test_applied_is_idempotent_and_receipt_restores_actual_status(self):
        from agents.reader_actions import acknowledge
        from database import database as db
        from database.models import TaskRequestRow
        result = acknowledge('task', self.receipt(), self.memory_repo)
        self.assertEqual(result['status'], 'applied')
        self.assertEqual(acknowledge('task', self.receipt(status='rejected'), self.memory_repo)['status'], 'applied')
        with db.session_scope() as session:
            self.assertEqual(session.get(TaskRequestRow, 'receipt').result['reader_actions'][0]['status'], 'applied')

    def test_wrong_identity_page_revision_and_epoch_refused(self):
        from agents.reader_actions import acknowledge
        from database.learning_tasks import TaskConflict
        for values in ({'student_id': 'other'}, {'session_id': 'other'}, {'task_revision': 2},
                       {'page': 1}, {'action_id': 'made-up'}, {'version': 'old'}):
            with self.subTest(values=values), self.assertRaises(TaskConflict):
                acknowledge('task', self.receipt(**values), self.memory_repo)
        self.memory_repo.memory_epoch = lambda *a: 1
        with self.assertRaises(TaskConflict):
            acknowledge('task', self.receipt(), self.memory_repo)

    def test_new_task_rejects_old_navigation(self):
        from agents.reader_actions import acknowledge
        from database.learning_tasks import TaskConflict, now
        from database import database as db
        from database.models import LearningTaskRow
        from datetime import timedelta
        with db.session_scope() as session:
            session.add(LearningTaskRow(id='new', student_id='s', session_id='session', created_at=now()+timedelta(seconds=1),
                expires_at=now()+timedelta(minutes=20)))
        with self.assertRaises(TaskConflict):
            acknowledge('task', self.receipt(), self.memory_repo)

    def test_missing_pdf_is_document_conflict(self):
        from agents.reader_actions import acknowledge
        from database.learning_tasks import TaskConflict
        self.path.unlink()
        with self.assertRaises(TaskConflict) as error:
            acknowledge('task', self.receipt(), self.memory_repo)
        self.assertEqual(error.exception.code, 'document_changed')
