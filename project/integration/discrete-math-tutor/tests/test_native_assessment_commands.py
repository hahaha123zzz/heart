"""原生测评命令、受控HTTP与rubric；真实SQLite，模型/教师输入为明确夹具。"""
from copy import deepcopy
import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from agents.context_sufficiency import EvidenceDecision
from deeptutor.learning.service import MasteryInteractionError
from integrations.deeptutor.assessment_commands import AssessmentCommands
from integrations.deeptutor.native_bridge import install_native_bridge
from integrations.deeptutor.native_contract import NativeTurnKey
from integrations.deeptutor.client import BackendUnavailable
from tests import test_native_assessment as fixtures
from tests import test_native_learning_tool_adapter as tool_fixtures


class AssessmentCommandTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.NativeAssessmentTests.asyncSetUp
    asyncTearDown = fixtures.NativeAssessmentTests.asyncTearDown
    finished = fixtures.NativeAssessmentTests.finished
    _collect = fixtures.NativeAssessmentTests._collect
    host_post = fixtures.NativeAssessmentTests.host_post
    pending = fixtures.NativeAssessmentTests.pending

    def register(self, commands, *, concept=False, qid='q1'):
        question = self.pending(question_id=qid, **({'knowledge_point_id': 'p2', 'question_type': 'open',
            'prompt': '请用自己的话解释相关与因果的区别。', 'options': [],
            'expected_answer': 'PRIVATE-RUBRIC-REFERENCE'} if concept else {}))
        rubric = [{'id': 'scope', 'description': '区分关联和因果推断'},
                  {'id': 'reason', 'description': '说明因果判断需要额外依据'}] if concept else []
        return commands.register('tool-path', question, reviewer_id='controlled-teacher', key_version='fixture-v1',
            sources=[fixtures.SOURCE], rubric=rubric,
            evidence_decision=EvidenceDecision(status='sufficient', source_ids=['q2-1'], reason='受控Q2核验输入'))

    async def test_actual_help_events_do_not_become_independent_mastery(self):
        with self.bridge.learning_service(self.request) as service:
            commands = AssessmentCommands(service)
            self.register(commands)
            commands.run('tool-path', 'q1', command_id='present', action='present')
            for level in (1, 2, 3):
                args = dict(command_id='hint'+str(level), action='help', kind='hint', level=level, published=True)
                commands.run('tool-path', 'q1', **args)
                commands.run('tool-path', 'q1', **args)
            commands.run('tool-path', 'q1', command_id='full', action='help', kind='explanation',
                         published=True, full_explanation=True)
            commands.run('tool-path', 'q1', command_id='answer', action='answer', text='A', confidence=.8)
            result = commands.run('tool-path', 'q1', command_id='grade', action='grade')
            self.assertEqual(result['assistance']['hints_used'], 3)
            self.assertTrue(result['assistance']['full_explanation_seen'])
            self.assertEqual(result['evidence_summary']['assisted'], 1)
            event = service.store.load('tool-path').learning_evidence[0]
            self.assertEqual(event.hints_used, 3)
            self.assertEqual(event.confidence, .8)
            self.assertFalse(service.store.load('tool-path').quiz_attempts[0].independent)
            self.assertEqual(service.store.load('tool-path').mastery_levels['p1'], 0.)
            self.assertLessEqual(event.quality, .6)
            replay = commands.run('tool-path', 'q1', command_id='grade', action='grade')
            self.assertEqual(replay, result)

    async def test_rubric_review_is_bound_to_actual_answer_and_can_be_voided(self):
        with self.bridge.learning_service(self.request) as service:
            commands = AssessmentCommands(service)
            self.register(commands, concept=True)
            commands.run('tool-path', 'q1', command_id='present', action='present')
            commands.run('tool-path', 'q1', command_id='answer', action='answer',
                         text='相关只表示关联，因果需要额外的实验控制依据。', confidence=.7)
            args = dict(command_id='review', action='review', reviewer_id='controlled-teacher',
                        criteria={'scope': 'met', 'reason': 'met'}, text='逐项核对已通过')
            graded = commands.run('tool-path', 'q1', **args)
            self.assertEqual(graded['status'], 'graded')
            self.assertEqual(graded['assessment']['version'], 'native-rubric-reviewed-v1')
            self.assertTrue(service.store.load('tool-path').qualitative_mastery['p2'])
            self.assertEqual(commands.run('tool-path', 'q1', **args), graded)
            with self.assertRaisesRegex(MasteryInteractionError, 'assessment_command_conflict'):
                commands.run('tool-path', 'q1', **dict(args, text='不同的复核说明'))
            commands.run('tool-path', 'q1', command_id='void', action='void', text='发现题干有歧义，撤销本次评估')
            progress = service.store.load('tool-path')
            self.assertNotIn('p2', progress.qualitative_mastery)
            self.assertFalse(progress.learning_evidence)

    async def test_unavailable_rubric_creates_no_negative_evidence(self):
        with self.bridge.learning_service(self.request) as service:
            commands = AssessmentCommands(service)
            self.register(commands, concept=True)
            commands.run('tool-path', 'q1', command_id='answer', action='answer', text='我认为存在关联。')
            result = commands.run('tool-path', 'q1', command_id='review', action='review',
                reviewer_id='controlled-teacher', criteria={'scope': 'met', 'reason': 'unavailable'})
            self.assertEqual(result['review_status'], 'ungraded')
            self.assertEqual(commands.status('tool-path', 'q1')['status'], 'answered')
            self.assertFalse(service.store.load('tool-path').learning_evidence)

    async def test_skip_retry_cannot_skip_a_different_question_and_defer_is_not_mastery(self):
        with self.bridge.learning_service(self.request) as service:
            commands = AssessmentCommands(service)
            self.register(commands)
            commands.run('tool-path', 'q1', command_id='skip', action='skip')
            self.register(commands, qid='q2')
            commands.run('tool-path', 'q1', command_id='skip', action='skip')
            self.assertEqual(service.store.get_active_interaction('tool-path').interaction_id, 'q2')
            commands.run('tool-path', 'q2', command_id='defer', action='defer', text='下次再练')
            progress = service.store.load('tool-path')
            self.assertIn('p1', progress.deferred_objectives)
            self.assertFalse(progress.quiz_attempts)
            self.assertFalse(progress.mastery_levels)

    async def test_correction_reuses_native_repair_with_a_new_reviewed_key(self):
        with self.bridge.learning_service(self.request) as service:
            commands = AssessmentCommands(service)
            self.register(commands)
            commands.run('tool-path', 'q1', command_id='answer', action='answer', text='B')
            commands.run('tool-path', 'q1', command_id='grade', action='grade')
            result = commands.correct('tool-path', 'q1', command_id='correct', expected_answer='B',
                reviewer_id='controlled-teacher', key_version='fixture-v2', sources=[fixtures.SOURCE], reason='核对后修订答案键')
            self.assertTrue(result['assessment']['is_correct'])
            self.assertEqual(len(service.store.load('tool-path').quiz_attempts), 1)
            self.assertEqual(service.store.load('tool-path').learning_evidence[0].visual_context['host_assessment']['key_version'], 'fixture-v2')

    async def test_misconception_is_a_quoted_hypothesis_and_deleted_epoch_blocks_it(self):
        with self.bridge.learning_service(self.request) as service:
            commands = AssessmentCommands(service)
            self.register(commands, concept=True)
            commands.run('tool-path', 'q1', command_id='answer', action='answer', text='相关就是因果。')
            commands.run('tool-path', 'q1', command_id='review', action='review', reviewer_id='controlled-teacher',
                         criteria={'scope': 'not_met', 'reason': 'not_met'})
            args = dict(misconception_type='correlation_causation_confusion', source_quote='相关就是因果')
            result = commands.run('tool-path', 'q1', command_id='hypothesis', action='hypothesis', **args)
            self.assertEqual(result['assessment']['misconception_hypotheses'][0]['status'], 'hypothesis')
            result = commands.run('tool-path', 'q1', command_id='dismiss', action='dismiss_hypothesis', **args)
            self.assertEqual(result['assessment']['misconception_hypotheses'][0]['status'], 'dismissed')
            tool_fixtures.NativeLearningToolAdapterTests.revoke(self)
            with self.assertRaises(BackendUnavailable):
                commands.status('tool-path', 'q1')

    async def test_interjections_preserve_question_and_text_option_is_gradable(self):
        with self.bridge.learning_service(self.request) as service:
            commands = AssessmentCommands(service)
            self.register(commands)
            from deeptutor.services.session.turns.learning_adapter import LearningTurnAdapter
            async def original_submit(turn, answer):
                return await LearningTurnAdapter._commit_mastery_card_answer(object(), path_id='tool-path',
                    session_id=self.entry['native_session_id'], turn_id=turn, question_id='q1', answer=answer)
            await original_submit('interjection', '请解释这个变量')
            self.assertFalse(service.store.get_interaction('tool-path', 'q1').user_answer)
            for index, message in enumerate(('我懂了', '请解释自变量', '答案错了', '只给提示', '我不会')):
                result = commands.run('tool-path', 'q1', command_id=str(index), action='message', text=message)
                self.assertEqual(result['message_action'], 'interjection')
                self.assertEqual(service.store.get_active_interaction('tool-path').interaction_id, 'q1')
                self.assertFalse(service.store.get_interaction('tool-path', 'q1').user_answer)
            commands.run('tool-path', 'q1', command_id='answer', action='message', text='自变量', confidence=.9)
            await original_submit('original-runtime-answer', '自变量')
            await original_submit('original-runtime-answer', '自变量')
            result = commands.run('tool-path', 'q1', command_id='grade', action='grade')
            self.assertTrue(result['assessment']['is_correct'])
            self.assertEqual(result['evidence_summary']['independent'], 1)
            with self.assertRaisesRegex(MasteryInteractionError, 'assessment_command_conflict'):
                commands.run('tool-path', 'q1', command_id='answer', action='answer', text='自变量', confidence=.1)

    async def test_unpublished_help_changed_source_and_tampered_key_are_blocked(self):
        with self.bridge.learning_service(self.request) as service:
            commands = AssessmentCommands(service)
            self.register(commands)
            with self.assertRaisesRegex(MasteryInteractionError, 'published_help_required'):
                commands.run('tool-path', 'q1', command_id='hint', action='help', kind='hint', level=1)
            self.assertEqual(commands.status('tool-path', 'q1')['assistance']['hints_used'], 0)
            self.verified_sources.return_value = []
            self.verified_sources.side_effect = None
            result = commands.status('tool-path', 'q1')
            self.assertIsNone(result['question'])
            self.assertNotIn('自变量', str(result))
            with self.assertRaisesRegex(MasteryInteractionError, 'assessment_source_unavailable'):
                commands.run('tool-path', 'q1', command_id='answer', action='answer', text='A')
            self.assertFalse(service.store.load('tool-path').learning_evidence)
            self.verified_sources.side_effect = lambda rows: deepcopy(rows)
            from deeptutor.learning.storage import LearningStore
            raw = LearningStore()
            def tamper(tx):
                item = tx.get_interaction('q1')
                item.question.expected_answer = 'B'
                tx.put_interaction(item)
            raw.mutate('tool-path', tamper)
            with self.assertRaisesRegex(MasteryInteractionError, 'assessment_question_changed'):
                commands.run('tool-path', 'q1', command_id='answer', action='answer', text='B')

    async def test_visual_question_without_pixel_evidence_cannot_be_registered(self):
        with self.bridge.learning_service(self.request) as service:
            commands = AssessmentCommands(service)
            question = self.pending(question_id='visual', visual_context={'image_id': 'missing-image'})
            with self.assertRaisesRegex(MasteryInteractionError, 'assessment_type_requires_review'):
                commands.register('tool-path', question, reviewer_id='controlled-teacher',
                    key_version='v1', sources=[fixtures.SOURCE])
            self.assertIsNone(service.store.get_active_interaction('tool-path'))
            self.assertFalse(service.store.load('tool-path').learning_evidence)

    async def test_private_http_entry_and_public_projection(self):
        app = FastAPI()
        with patch.dict(os.environ, DEEPTUTOR_NATIVE_ENABLED='1'):
            install_native_bridge(app, self.sessions)
            with TestClient(app) as client:
                root = self.request.model_dump(include=set(NativeTurnKey.model_fields))
                key = root | {'path_id': 'tool-path', 'question_id': 'q1'}
                headers = {'X-Heart-Bridge-Token': 't'*32}
                self.assertEqual(client.post('/internal/heart/native/assessment/status', json=key).status_code, 401)
                registration = root | {'path_id': 'tool-path', 'question': self.pending(question_id='q1').model_dump(mode='json'),
                    'reviewer_id': 'controlled-teacher', 'key_version': 'fixture-v1', 'sources': [fixtures.SOURCE],
                    'evidence_decision': {'status': 'sufficient', 'source_ids': ['q2-1'], 'reason': '受控Q2核验'}}
                result = client.post('/internal/heart/native/assessment/register', json=registration, headers=headers)
                self.assertEqual(result.status_code, 200, result.text)
                self.assertNotIn('expected_answer', result.text)
                self.assertNotIn('host_assessment', result.text)
                self.assertEqual(client.post('/internal/heart/native/assessment/action', headers=headers,
                    json=key | {'command_id': 'a1', 'action': 'answer', 'text': 'A', 'expected_answer': 'A'}).status_code, 422)
                for cid, action, extra in (('present', 'present', {}), ('answer', 'answer', {'text': 'A'}), ('grade', 'grade', {})):
                    response = client.post('/internal/heart/native/assessment/action', headers=headers,
                        json=key | {'command_id': cid, 'action': action} | extra)
                    self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()['status'], 'graded')
                self.assertEqual(response.json()['evidence_summary']['independent'], 1)
                self.assertNotIn('PRIVATE-', response.text)
