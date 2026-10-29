"""TA3真实原生存储/接口；题目审核及教材输入受控。"""
import asyncio
from copy import deepcopy
import json
import os
import unittest
from unittest.mock import patch
from deeptutor.learning.service import MasteryInteractionError
from integrations.deeptutor.learning_cards import NativeLearningCards
from integrations.deeptutor.assessment_commands import AssessmentCommands
from tests import test_native_assessment_commands as fixtures


class NativeLearningCardTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.AssessmentCommandTests.asyncSetUp
    asyncTearDown = fixtures.AssessmentCommandTests.asyncTearDown
    finished = fixtures.AssessmentCommandTests.finished
    _collect = fixtures.AssessmentCommandTests._collect
    host_post = fixtures.AssessmentCommandTests.host_post
    pending = fixtures.AssessmentCommandTests.pending
    register = fixtures.AssessmentCommandTests.register

    def prepare(self, service):
        service.store.bind_session('tool-path', self.entry['native_session_id'])
        commands = AssessmentCommands(service)
        self.register(commands)
        cards = NativeLearningCards(commands)
        deck = cards.configure('tool-path', 'q1', hints=['先找主动改变的条件。', '区分操纵和测量。', '操纵的条件是自变量。'],
            full_explanation='研究者主动操纵的是自变量，观察测量的是因变量。', presentations=[
                {'card_kind': 'step_reveal', 'explanation_steps': [
                    {'title': '操纵', 'body': '先找主动改变的条件。'}, {'title': '测量', 'body': '再找观察到的反应。'}]},
                {'card_kind': 'concept_comparison', 'comparison_labels': ['自变量', '因变量'],
                 'comparison_rows': [{'aspect': '角色', 'left': '操纵的条件', 'right': '测量的反应'}]}])
        return cards, deck

    def act(self, cards, deck, action, command_id, **extra):
        card = deck['learning_cards'][0]
        return cards.act('tool-path', 'q1', card_id=card['card_id'], action=action,
            command_id=command_id, base_revision=deck['revision'], **extra)

    async def test_private_explanation_is_not_in_dom_before_requested_and_three_hints_persist(self):
        with self.bridge.learning_service(self.request) as service:
            cards, deck = self.prepare(service)
            self.assertNotIn('研究者主动操纵的是自变量，观察测量的是因变量。', json.dumps(deck, ensure_ascii=False))
            self.assertNotIn('expected_answer', json.dumps(deck))
            self.assertEqual(len(deck['learning_cards']), 2)
            from deeptutor.capabilities.mastery.tools import MasteryNoteExplainedTool
            await MasteryNoteExplainedTool().execute(_mastery_path_id='tool-path', _mastery_session_mode='study',
                knowledge_point_id='p1', summary='已经讲解变量的操纵与测量')
            deck = cards.deck('tool-path', 'q1')
            self.assertTrue(deck['learning_cards'][-1]['explained'])
            for n in range(1, 4):
                previous = deepcopy(deck)
                deck = self.act(cards, deck, 'request_hint', f'h{n}')
                self.assertEqual(deck['learning_cards'][0]['feedback']['level'], n)
                self.assertEqual(self.act(cards, previous, 'request_hint', f'h{n}'), deck)
            deck = self.act(cards, deck, 'view_explanation', 'full')
            self.assertEqual(len(deck['learning_cards']), 4)
            self.assertEqual(deck['learning_cards'][0]['assistance']['hints_used'], 3)
            step = deck['learning_cards'][1]
            updated = cards.act('tool-path', 'q1', card_id=step['card_id'], action='set_expanded',
                command_id='expand', base_revision=deck['revision'], expanded=[0, 1])
            restored = NativeLearningCards(AssessmentCommands(service)).deck('tool-path', 'q1')
            self.assertEqual(updated, restored)
            self.assertEqual(restored['learning_cards'][1]['expanded'], [0, 1])
            graded = self.act(cards, restored, 'submit_answer', 'answer', text='A')
            self.assertEqual(graded['learning_cards'][0]['assessment']['is_correct'], True)
            self.assertEqual(graded['learning_cards'][-1]['evidence_summary']['assisted'], 1)
            self.assertFalse(service.store.load('tool-path').quiz_attempts[0].independent)
            from tests.test_native_assessment import SOURCE
            cards.commands.correct('tool-path', 'q1', command_id='key-revised', expected_answer='B',
                reviewer_id='controlled-teacher', key_version='v2', sources=[SOURCE], reason='核验后修订键')
            revised = cards.deck('tool-path', 'q1')
            self.assertIsNone(revised['learning_cards'][0]['feedback'])
            self.assertEqual(len(revised['learning_cards']), 2)

    async def test_stale_and_parallel_submissions_only_have_one_effective_result(self):
        with self.bridge.learning_service(self.request) as service:
            cards, deck = self.prepare(service)
            results = await asyncio.gather(*(asyncio.to_thread(self.act, cards, deck,
                'submit_answer', f'answer{i}', text='A') for i in (1, 2)), return_exceptions=True)
            self.assertEqual(sum(isinstance(r, dict) for r in results), 1)
            self.assertEqual(len(service.store.load('tool-path').quiz_attempts), 1)
            self.assertEqual(len(service.store.load('tool-path').learning_evidence), 1)

    async def test_retry_after_committed_grade_but_missing_card_receipt_does_not_rescore(self):
        with self.bridge.learning_service(self.request) as service:
            cards, deck = self.prepare(service)
            mutate = service.store.mutate
            def fail_finish(path, fn, **kwargs):
                if fn.__name__ == 'finish':
                    raise OSError('模拟评分后响应中断')
                return mutate(path, fn, **kwargs)
            with patch.object(service.store, 'mutate', side_effect=fail_finish):
                with self.assertRaises(OSError):
                    self.act(cards, deck, 'submit_answer', 'retry', text='A')
            restored = self.act(cards, deck, 'submit_answer', 'retry', text='A')
            self.assertEqual(restored['learning_cards'][0]['status'], 'graded')
            self.assertEqual(len(service.store.load('tool-path').quiz_attempts), 1)
            with self.assertRaisesRegex(MasteryInteractionError, 'assessment_command_conflict'):
                self.act(cards, deck, 'submit_answer', 'retry', text='B')

    async def test_defer_return_and_source_loss_never_generate_a_mastery_result(self):
        with self.bridge.learning_service(self.request) as service:
            cards, deck = self.prepare(service)
            returned = self.act(cards, deck, 'return_path', 'return')
            self.assertEqual(returned['navigation'], {'path_id': 'tool-path', 'objective_id': 'p1'})
            self.assertIsNotNone(service.store.get_active_interaction('tool-path'))
            deferred = self.act(cards, returned, 'defer', 'defer')
            self.assertEqual(deferred['learning_cards'][0]['disposition'], 'defer')
            self.assertFalse(service.store.load('tool-path').learning_evidence)
            self.assertIn('p1', service.store.load('tool-path').deferred_objectives)
            self.verified_sources.side_effect = lambda rows: []
            self.assertEqual(cards.deck('tool-path', 'q1')['learning_cards'], [])

    async def test_host_proxy_reaches_real_native_http_and_restores_committed_score(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from integrations.deeptutor.native_bridge import install_native_bridge
        from integrations.deeptutor.native_contract import NativeTurnKey
        from integrations.deeptutor.client import BackendUnavailable
        from database.repository import Repository
        from learning_cards_api import router
        with self.bridge.learning_service(self.request) as service:
            cards, deck = self.prepare(service)
        key = self.request.model_dump(include=set(NativeTurnKey.model_fields)) | {'path_id': 'tool-path', 'question_id': 'q1', 'memory_epoch': 0}
        conversation_id = Repository().append_conversation('s', 'assistant', '已登记测评', session_id='sess', selection_ref={
            'section_title': '变量', '_native_assessment': key,
            'learning_cards': [dict(card, memory_epoch=0) for card in deck['learning_cards']]})
        private, host = FastAPI(), FastAPI()
        with patch.dict(os.environ, DEEPTUTOR_NATIVE_ENABLED='1'), patch('knowledge.course_config.COURSE_ID', 'course-1'), patch('knowledge.pdf_reader.document', return_value={'version': 'v1'}):
            install_native_bridge(private, self.sessions);host.include_router(router)
            with TestClient(private) as native_client, TestClient(host) as host_client:
                def route(path, payload):
                    if path.startswith('/internal/heart/native/assessment/'):
                        response = native_client.post(path, json=payload, headers={'X-Heart-Bridge-Token': 't'*32})
                        if response.status_code != 200:
                            raise BackendUnavailable(response.text)
                        return response.json()
                    return self.host_post(path, payload)
                with patch('integrations.deeptutor.client.DeepTutorBackend._post', side_effect=route):
                    payload = {'student_id': 's', 'session_id': 'sess', 'conversation_id': conversation_id,
                        'card_id': deck['learning_cards'][0]['card_id'], 'command_id': 'proxy-answer',
                        'base_revision': deck['revision'], 'action': 'submit_answer', 'text': 'A'}
                    response = host_client.post('/api/learning/cards/action', json=payload)
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.json()['learning_cards'][0]['status'], 'graded')
                    replay = host_client.post('/api/learning/cards/action', json=payload)
                    self.assertEqual(response.json(), replay.json())
                    restored = host_client.post('/api/learning/cards/view', json={k: payload[k] for k in ('student_id', 'session_id', 'conversation_id')})
                    self.assertEqual(restored.status_code, 200, restored.text)
                    self.assertEqual(restored.json()['learning_cards'][0]['learner_answer'], 'A')
                    self.assertNotIn('expected_answer', restored.text)
                    self.assertNotIn('_native_assessment', str(Repository().get_conversation_with_figures('s')))
