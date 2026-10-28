"""原生真实题目事务；来源核验和教师审核输入受控，不冒充正式页面验收。"""
import asyncio
from copy import deepcopy
import json
import unittest
from unittest.mock import AsyncMock, patch

from deeptutor.learning.models import PendingQuestion, PendingOption, KnowledgeType, KnowledgePoint
from deeptutor.learning.service import MasteryInteractionError
from integrations.deeptutor.assessment_store import reviewed_question
from tests import test_native_learning_tool_adapter as fixtures

SOURCE = {'source_id': 'q2-1', 'document_id': 'doc', 'version': 'v1',
          'text': '自变量是研究者操纵的变量。',
          'location': {'evidence': {'quote': '自变量是研究者操纵的变量。', 'document_version': 'v1'}}}


class NativeAssessmentTests(unittest.IsolatedAsyncioTestCase):
    finished = fixtures.NativeLearningToolAdapterTests.finished
    _collect = fixtures.NativeLearningToolAdapterTests._collect
    host_post = fixtures.NativeLearningToolAdapterTests.host_post

    async def asyncSetUp(self):
        await fixtures.NativeLearningToolAdapterTests.asyncSetUp(self)
        from deeptutor.learning.storage import LearningStore
        with self.bridge.scope(self.entry):
            store = LearningStore()
            progress = store.load('tool-path')
            progress.modules[0].knowledge_points[0].type = KnowledgeType.MEMORY
            progress.knowledge_types['p1'] = KnowledgeType.MEMORY
            progress.modules[0].knowledge_points.append(KnowledgePoint(id='p2', name='解释变量', type='concept', module_id='m1'))
            progress.knowledge_types['p2'] = KnowledgeType.CONCEPT
            store.save(progress)
        self.source_check = patch('agents.adaptive_tutoring.verified_sources', side_effect=lambda rows: deepcopy(rows))
        self.verified_sources = self.source_check.start()

    async def asyncTearDown(self):
        self.source_check.stop()
        await fixtures.NativeLearningToolAdapterTests.asyncTearDown(self)

    def pending(self, **changes):
        return PendingQuestion(**(dict(question_id='reviewed-1', knowledge_point_id='p1', module_id='m1',
            prompt='研究者主动改变的变量称作什么？', question_type='choice', expected_answer='A',
            options=[PendingOption(label='A', body='自变量'), PendingOption(label='B', body='因变量')]) | changes))

    def register(self, service, pending=None):
        pending = pending or self.pending()
        with reviewed_question('tool-path', pending, reviewer_id='controlled-teacher',
                               key_version='fixture-key-v1', sources=[SOURCE]):
            result = service.register_question('tool-path', pending, session_id=self.entry['native_session_id'])
        service.mark_question_awaiting('tool-path', interaction_id=pending.question_id)
        return result

    async def test_unreviewed_question_rolls_back_registration_and_event(self):
        with self.bridge.learning_service(self.request) as service:
            before = service.store.load('tool-path').version
            events = service.store.list_events('tool-path')
            with self.assertRaisesRegex(MasteryInteractionError, 'question_review_required'):
                service.register_question('tool-path', self.pending())
            self.assertIsNone(service.store.get_active_interaction('tool-path'))
            self.assertEqual(service.store.load('tool-path').version, before)
            self.assertEqual(service.store.list_events('tool-path'), events)

    async def test_original_tools_present_freeze_grade_and_restore_exactly_once(self):
        from deeptutor.capabilities.mastery.tools import MasteryQuizTool, MasteryGradeTool
        from deeptutor.learning.pending import public_pending_question
        with self.bridge.learning_service(self.request) as service:
            self.register(service)
            ended = []
            card = await MasteryQuizTool().execute(_mastery_path_id='tool-path',
                _mastery_session_mode='study', knowledge_point_id='p1', question='不能覆盖原题',
                expected_answer='B', _end_turn_on_card=lambda: ended.append(True))
            self.assertTrue(card.success, card.content)
            self.assertEqual(ended, [True])
            self.assertEqual(card.metadata['mastery_quiz']['question_id'], 'reviewed-1')
            self.assertNotIn('expected_answer', json.dumps(card.metadata))
            service.record_question_answer('tool-path', 'A', interaction_id='reviewed-1')
            with patch('deeptutor.capabilities.mastery.tools._sync_mastery_attempt_to_question_bank', new_callable=AsyncMock):
                result = await MasteryGradeTool().execute(_mastery_path_id='tool-path',
                    _mastery_session_mode='study', answer='B', question_id='reviewed-1')
            self.assertTrue(result.success, result.content)
            progress, interaction, replayed = service.grade_interaction('tool-path', answer='B', question_id='reviewed-1')
            self.assertTrue(replayed)
            self.assertEqual(interaction.user_answer, 'A')
            self.assertTrue(interaction.result['is_correct'])
            self.assertEqual(len(progress.quiz_attempts), 1)
            self.assertEqual(len(progress.learning_evidence), 1)
            self.assertEqual(interaction.result['assessment_version'], 'native-choice-reviewed-v1')
            self.assertEqual(progress.learning_evidence[0].visual_context['verification'], 'reviewed_key')
            self.assertNotIn('expected_answer', public_pending_question(interaction.question).to_dict())
        with self.bridge.learning_service(self.request) as restored:
            self.assertEqual(restored.store.get_interaction('tool-path', 'reviewed-1').status.value, 'graded')
            self.assertEqual(len(restored.store.load('tool-path').quiz_attempts), 1)

    async def test_help_or_unclear_choice_preserves_pending_without_evidence(self):
        with self.bridge.learning_service(self.request) as service:
            self.register(service)
            for message in ('只给提示', '我懂了', '为什么不是因变量？', '先跳过'):
                with self.subTest(message=message), self.assertRaisesRegex(MasteryInteractionError, 'answer_needs_clarification'):
                    service.record_question_answer('tool-path', message, interaction_id='reviewed-1')
            progress = service.store.load('tool-path')
            self.assertEqual(service.store.get_active_interaction('tool-path').status.value, 'awaiting_input')
            self.assertFalse(progress.learning_evidence)
            self.assertFalse(progress.quiz_attempts)

    async def test_grade_cannot_invent_a_student_answer_or_override_the_key(self):
        with self.bridge.learning_service(self.request) as service:
            self.register(service)
            with self.assertRaisesRegex(MasteryInteractionError, 'student_answer_not_recorded'):
                service.grade_interaction('tool-path', answer='A', question_id='reviewed-1')
            service.record_question_answer('tool-path', 'B', interaction_id='reviewed-1')
            with self.assertRaisesRegex(MasteryInteractionError, 'assessment_answer_changed'):
                service.grade_interaction('tool-path', answer='B', question_id='reviewed-1', expected_answer='B')
            self.assertFalse(service.store.load('tool-path').quiz_attempts)

    async def test_source_loss_produces_no_negative_mastery(self):
        with self.bridge.learning_service(self.request) as service:
            self.register(service)
            service.record_question_answer('tool-path', 'B', interaction_id='reviewed-1')
            self.verified_sources.side_effect = lambda rows: []
            with self.assertRaisesRegex(MasteryInteractionError, 'assessment_source_unavailable'):
                service.grade_interaction('tool-path', answer='B', question_id='reviewed-1')
            progress = service.store.load('tool-path')
            self.assertFalse(progress.quiz_attempts)
            self.assertFalse(progress.mastery_levels)
            self.assertEqual(service.store.get_active_interaction('tool-path').status.value, 'answered')

    async def test_concurrent_grade_records_only_one_attempt(self):
        with self.bridge.learning_service(self.request) as service:
            self.register(service)
            service.record_question_answer('tool-path', 'A', interaction_id='reviewed-1')
            results = await asyncio.gather(*(asyncio.to_thread(service.grade_interaction,
                'tool-path', answer='A', question_id='reviewed-1') for _ in range(2)))
            self.assertEqual(sorted(result[2] for result in results), [False, True])
            self.assertEqual(len(service.store.load('tool-path').learning_evidence), 1)

    async def test_unreviewed_concept_or_assisted_answer_cannot_receive_independent_mastery(self):
        from deeptutor.capabilities.mastery.tools import MasteryNoteExplainedTool
        with self.bridge.learning_service(self.request) as service:
            with self.assertRaisesRegex(MasteryInteractionError, 'qualitative_rubric_review_required'):
                service.record_qualitative_for_path('tool-path', 'p2', passed=True, evidence='模型自称已掌握')
            self.register(service)
            result = await MasteryNoteExplainedTool().execute(_mastery_path_id='tool-path',
                _mastery_session_mode='study', knowledge_point_id='p1', summary='已经解释过这道题')
            self.assertTrue(result.success)
            service.record_question_answer('tool-path', 'A', interaction_id='reviewed-1')
            progress, _, _ = service.grade_interaction('tool-path', answer='A', question_id='reviewed-1')
            self.assertFalse(progress.qualitative_mastery)
            self.assertFalse(progress.quiz_attempts[0].independent)
            self.assertEqual(progress.mastery_levels['p1'], 0.)


if __name__ == '__main__':
    unittest.main()
