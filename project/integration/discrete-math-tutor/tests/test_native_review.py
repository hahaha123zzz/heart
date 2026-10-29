"""原生复习：隔离SQLite、可注入时钟，审核/来源输入受控。"""
import asyncio
from copy import deepcopy
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from deeptutor.learning.service import MasteryInteractionError
from integrations.deeptutor.assessment_commands import AssessmentCommands
from integrations.deeptutor.review import NativeReviewService, scheduler
from tests import test_native_learning_cards as fixtures


class NativeReviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_authorization_timeout_is_retryable_but_deleted_owner_is_conflict(self):
        from urllib.error import HTTPError
        from fastapi import HTTPException
        from integrations.deeptutor.client import BackendUnavailable
        entry = self.bridge.entry(self.request)
        timeout = BackendUnavailable('暂时无法回查')
        timeout.__cause__ = TimeoutError('受控响应丢失')
        denied = BackendUnavailable('账户已失效')
        denied.__cause__ = HTTPError('http://127.0.0.1/internal',409,'deleted',{},None)
        for error, expected in ((timeout,503),(denied,409)):
            with patch('integrations.deeptutor.client.DeepTutorBackend.authorize_native_assessment',side_effect=error):
                with self.assertRaises(HTTPException) as caught:
                    await self.bridge.authorize_assessment(self.request,entry)
                self.assertEqual(caught.exception.status_code,expected)

    asyncSetUp = fixtures.NativeLearningCardTests.asyncSetUp
    asyncTearDown = fixtures.NativeLearningCardTests.asyncTearDown
    finished = fixtures.NativeLearningCardTests.finished
    _collect = fixtures.NativeLearningCardTests._collect
    host_post = fixtures.NativeLearningCardTests.host_post
    pending = fixtures.NativeLearningCardTests.pending
    register = fixtures.NativeLearningCardTests.register
    prepare = fixtures.NativeLearningCardTests.prepare

    def assessed(self, service):
        self.prepare(service)
        commands = AssessmentCommands(service)
        commands.run('tool-path', 'q1', command_id='initial-answer', action='answer', text='A')
        commands.run('tool-path', 'q1', command_id='initial-grade', action='grade')
        progress = service.store.load('tool-path')
        self.moment = progress.repetition_states['p1'].next_review_at + 3600
        return commands, NativeReviewService(commands, clock=lambda: self.moment)

    def act(self, review, queue, action, command_id, **kwargs):
        return review.act('tool-path', review_id=queue['reviews'][0]['review_id'],
            action=action, command_id=command_id, base_revision=queue['revision'], **kwargs)

    async def test_due_schedule_defer_restore_and_no_automatic_mode_or_pointer_change(self):
        with self.bridge.learning_service(self.request) as service:
            with patch.dict(os.environ, LEARNING_DEBUG='1'):
                commands, review = self.assessed(service)
                self.assertFalse(scheduler().DEBUG_MODE)
            before = service.store.load('tool-path')
            queue = review.queue('tool-path')
            self.assertEqual(queue['reviews'][0]['status'], 'due')
            self.assertFalse(queue['changes_learning_mode'])
            self.assertNotIn('forgetting_risk', str(queue))
            state = before.repetition_states['p1'].model_dump()
            delayed = self.act(review, queue, 'defer', 'defer-1')
            self.assertEqual(delayed['reviews'][0]['status'], 'deferred')
            self.assertEqual(self.act(review, queue, 'defer', 'defer-1'), delayed)
            restored = NativeReviewService(commands, clock=lambda: self.moment).queue('tool-path')
            self.assertEqual(delayed['reviews'], restored['reviews'])
            after = service.store.load('tool-path')
            self.assertEqual(after.repetition_states['p1'].model_dump(), state)
            self.assertEqual((after.current_module_id, after.current_kp_index, after.current_stage),
                (before.current_module_id, before.current_kp_index, before.current_stage))
            self.assertEqual(len(after.learning_evidence), 1)

    async def test_explicit_review_uses_new_question_and_finishes_exactly_once(self):
        with self.bridge.learning_service(self.request) as service:
            commands, review = self.assessed(service)
            queue = review.queue('tool-path')
            started = self.act(review, queue, 'start', 'start-1')
            child = started['question_id']
            self.assertNotEqual(child, 'q1')
            self.assertEqual(self.act(review, queue, 'start', 'start-1')['question_id'], child)
            with self.assertRaisesRegex(MasteryInteractionError, 'review_ungraded'):
                self.act(review, started, 'finish', 'not-graded')
            commands.run('tool-path', child, command_id='review-answer', action='answer', text='A')
            record = service._record_quiz_evidence
            def at_review_time(*args, **kwargs):
                event = record(*args, **kwargs)
                event.timestamp = self.moment
                return event
            with patch.object(service, '_record_quiz_evidence', side_effect=at_review_time):
                commands.run('tool-path', child, command_id='review-grade', action='grade')
            waiting = review.queue('tool-path')
            self.assertEqual(waiting['reviews'][0]['status'], 'active')
            done = self.act(review, waiting, 'finish', 'finish-1')
            self.assertEqual(self.act(review, waiting, 'finish', 'finish-1'), done)
            progress = service.store.load('tool-path')
            self.assertEqual(len(progress.learning_evidence), 2)
            self.assertEqual(progress.repetition_states['p1'].review_count, 2)
            self.assertEqual(progress.pending_question, None)
            self.assertEqual(sum(e.event_type == 'review.finish' for e in service.store.list_events('tool-path')), 1)

    async def test_return_preserves_position_and_restart_keeps_same_episode_assistance(self):
        with self.bridge.learning_service(self.request) as service:
            commands, review = self.assessed(service)
            queue = review.queue('tool-path')
            first = self.act(review, queue, 'start', 'start-1')
            commands.run('tool-path', first['question_id'], command_id='hint', action='help', published=True, kind='hint', level=1)
            returned = self.act(review, review.queue('tool-path'), 'return', 'return-1')
            self.assertIsNone(service.store.get_active_interaction('tool-path'))
            second = self.act(review, returned, 'start', 'start-2')
            self.assertNotEqual(first['question_id'], second['question_id'])
            commands.run('tool-path', second['question_id'], command_id='answer-2', action='answer', text='A')
            commands.run('tool-path', second['question_id'], command_id='grade-2', action='grade')
            self.assertFalse(service.store.load('tool-path').quiz_attempts[-1].independent)

    async def test_concept_review_requires_rubric_and_does_not_auto_score_an_open_answer(self):
        with self.bridge.learning_service(self.request) as service:
            service.store.bind_session('tool-path', self.entry['native_session_id'])
            commands = AssessmentCommands(service)
            self.register(commands, concept=True)
            commands.run('tool-path', 'q1', command_id='a', action='answer', text='相关表示共同变化，因果还需额外控制依据。')
            commands.run('tool-path', 'q1', command_id='r', action='review', reviewer_id='controlled-teacher',
                criteria={'scope': 'met', 'reason': 'met'})
            review = NativeReviewService(commands)
            started = self.act(review, review.queue('tool-path'), 'start', 'concept-start')
            commands.run('tool-path', started['question_id'], command_id='ra', action='answer', text='关联不能单独证明因果。')
            with self.assertRaisesRegex(MasteryInteractionError, 'review_ungraded'):
                self.act(review, review.queue('tool-path'), 'finish', 'early')
            self.assertEqual(len(service.store.load('tool-path').learning_evidence), 1)
            commands.run('tool-path', started['question_id'], command_id='rr', action='review', reviewer_id='controlled-teacher',
                criteria={'scope': 'met', 'reason': 'met'})
            self.act(review, review.queue('tool-path'), 'finish', 'concept-finish')
            self.assertEqual(len(service.store.load('tool-path').learning_evidence), 2)

    async def test_source_loss_and_void_block_review_without_negative_evidence(self):
        with self.bridge.learning_service(self.request) as service:
            commands, review = self.assessed(service)
            state = deepcopy(service.store.load('tool-path').repetition_states)
            queue = review.queue('tool-path')
            self.verified_sources.side_effect = lambda rows: []
            unavailable = review.queue('tool-path')
            self.assertEqual(unavailable['reviews'][0]['status'], 'source_unavailable')
            self.assertEqual(unavailable['reviews'][0]['allowed_actions'], [])
            with self.assertRaisesRegex(MasteryInteractionError, 'assessment_source_unavailable'):
                self.act(review, queue, 'start', 'bad-source')
            self.assertEqual(service.store.load('tool-path').repetition_states, state)
            self.verified_sources.side_effect = lambda rows: deepcopy(rows)
            commands.run('tool-path', 'q1', command_id='void', action='void', text='撤销不可靠题目')
            self.assertFalse(service.store.load('tool-path').repetition_states)
            self.assertEqual(review.queue('tool-path')['reviews'], [])

    async def test_parallel_start_cannot_replace_another_pending_question(self):
        with self.bridge.learning_service(self.request) as service:
            _, review = self.assessed(service)
            queue = review.queue('tool-path')
            results = await asyncio.gather(*(asyncio.to_thread(self.act, review, queue, 'start', f'start-{n}')
                for n in (1, 2)), return_exceptions=True)
            self.assertEqual(sum(isinstance(r, dict) for r in results), 1)
            self.assertEqual(len(service.store.load('tool-path').learning_evidence), 1)

    async def test_application_review_api_runs_native_cards_and_projects_only_once(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from integrations.deeptutor.native_bridge import install_native_bridge
        from integrations.deeptutor.native_contract import NativeTurnKey
        from integrations.deeptutor.client import BackendUnavailable
        from integrations.deeptutor.learning_cards import NativeLearningCards
        from database.repository import Repository
        from review_api import router as review_router
        from learning_cards_api import router as card_router
        with self.bridge.learning_service(self.request) as service:
            commands, review = self.assessed(service)
            deck = NativeLearningCards(commands).deck('tool-path', 'q1')
        binding = self.request.model_dump(include=set(NativeTurnKey.model_fields)) | {'path_id': 'tool-path', 'question_id': 'q1', 'memory_epoch': 0}
        source = Repository().append_conversation('s', 'assistant', '原学习回答', session_id='sess', selection_ref={
            'section_title': '变量', '_native_assessment': binding, 'learning_cards': [dict(c, memory_epoch=0) for c in deck['learning_cards']]})
        private, host = FastAPI(), FastAPI()
        with patch.dict(os.environ, DEEPTUTOR_NATIVE_ENABLED='1'), patch('knowledge.course_config.COURSE_ID', 'course-1'), patch('knowledge.pdf_reader.document', return_value={'version': 'v1'}):
            install_native_bridge(private, self.sessions);host.include_router(review_router);host.include_router(card_router)
            with TestClient(private) as native_client, TestClient(host) as client:
                def route(path, payload):
                    if path.startswith('/internal/heart/native/assessment/'):
                        response = native_client.post(path, json=payload, headers={'X-Heart-Bridge-Token': 't'*32})
                        if response.status_code != 200:
                            raise BackendUnavailable(response.text)
                        return response.json()
                    return self.host_post(path, payload)
                with patch('integrations.deeptutor.client.DeepTutorBackend._post', side_effect=route):
                    queued = client.get('/api/learning/reviews', params={'student_id': 's', 'session_id': 'sess'}).json()['reviews'][0]
                    payload = {'student_id': 's', 'session_id': 'sess', 'conversation_id': source, 'review_id': queued['review_id'],
                        'command_id': 'start', 'base_revision': queued['revision'], 'action': 'start'}
                    response = client.post('/api/learning/reviews/action', json=payload)
                    self.assertEqual(response.status_code, 200, response.text)
                    started = response.json()
                    self.assertNotEqual(started['conversation_id'], source)
                    self.assertEqual(client.post('/api/learning/reviews/action', json=payload).json()['conversation_id'], started['conversation_id'])
                    answer = {'student_id': 's', 'session_id': 'sess', 'conversation_id': started['conversation_id'],
                        'card_id': started['learning_cards'][0]['card_id'], 'command_id': 'answer', 'base_revision': started['revision'],
                        'action': 'submit_answer', 'text': 'A'}
                    graded = client.post('/api/learning/cards/action', json=answer)
                    self.assertEqual(graded.status_code, 200, graded.text)
                    pending = client.get('/api/learning/reviews', params={'student_id': 's', 'session_id': 'sess'}).json()['reviews'][0]
                    finished = client.post('/api/learning/reviews/action', json=payload | {'action': 'finish', 'command_id': 'finish', 'base_revision': pending['revision']})
                    self.assertEqual(finished.status_code, 200, finished.text)
                    self.assertEqual(len(Repository().get_conversation_with_figures('s')), 2)
                    self.assertNotIn('expected_answer', finished.text)
                    self.assertEqual(client.post('/api/learning/reviews/action', json=payload | {'path_id': 'evil'}).status_code, 422)

    async def test_unverified_old_observation_does_not_replace_formal_review_evidence(self):
        with self.bridge.learning_service(self.request) as service:
            _, review = self.assessed(service)
            original = review.queue('tool-path')['reviews'][0]
            from deeptutor.learning.models import LearningEvidence
            def observe(tx):
                tx.progress.learning_evidence.append(LearningEvidence(knowledge_point_id='p1', source='host_formative'))
                tx.touch()
            service.store.mutate('tool-path', observe)
            self.assertEqual(review.queue('tool-path')['reviews'][0]['review_id'], original['review_id'])

    async def test_legacy_type_map_is_derived_from_existing_objective_without_invented_default(self):
        with self.bridge.learning_service(self.request) as service:
            def clear_map(tx):
                tx.progress.knowledge_types.clear();tx.touch()
            service.store.mutate('tool-path', clear_map)
            _, review = self.assessed(service)
            self.assertEqual(service.store.load('tool-path').knowledge_types['p1'].value, 'memory')
            self.assertEqual(len(review.queue('tool-path')['reviews']), 1)
