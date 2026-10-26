"""历史辅导回顾只读投影，不恢复过期题目或更新正式学习状态。"""
from copy import deepcopy
import datetime as dt
import json
import unittest
from uuid import uuid4
from types import SimpleNamespace
from unittest.mock import patch
from sqlalchemy import select
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database.database import session_scope
from database.models import LearningTaskRow, LearningEventRow, ConversationRow, PDFCitationRow
from database.learning_tasks import LearningTaskRepository
from agents.deeptutor_learning.models import LearningProgress
from agents.learning_cards import build_learning_cards
from models.chat_request import ChatRequest
from agents.review_followups import review_followups
from tests.test_adaptive_tutoring import prior
from tests import test_memory_jobs as fixtures


class ReviewFollowupTests(unittest.TestCase):
    setUp = fixtures.MemoryJobTests.setUp
    tearDown = fixtures.MemoryJobTests.tearDown
    count = fixtures.MemoryJobTests.count

    def state(self, *, pending=True, verdict=None):
        state = prior(pending=pending)
        state['progress']['book_id'] = 'course-test'
        if verdict:
            point = state['progress']['modules'][0]['knowledge_points'][0]['id']
            state['progress']['learning_evidence'] = [{'knowledge_point_id': point,
                'source': 'host_formative', 'result': verdict}]
        return state

    def add(self, state=None, *, student='s', session='tab-a', epoch=0, status='completed',
            committed=True, age=0, point=None):
        self.memory.ensure_student(student)
        now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(seconds=age)
        state = deepcopy(state if state is not None else self.state())
        with session_scope() as db:
            db.add(LearningTaskRow(id=uuid4().hex, student_id=student, session_id=session,
                knowledge_point=point or self.point, status=status, revision=3, epoch=epoch,
                context={'tutoring': state},
                payload={'reader_location': {'chapter_id': 2, 'section_id': 2}},
                result={'answer_status': 'answered', 'memory_commit': {'status': 'committed' if committed else 'failed'}},
                created_at=now, expires_at=now+dt.timedelta(minutes=30)))
        if status == 'completed' and committed:
            progress = LearningProgress.model_validate(state['progress'])
            objective = progress.modules[0].knowledge_points[0].model_copy(update={'name': point or self.point})
            request = ChatRequest(student_id=student, session_id=session, request_id=uuid4().hex,
                message='历史辅导记录', reader_location={'chapter_id': 2, 'section_id': 2})
            cards = build_learning_cards(SimpleNamespace(request=request, progress=progress,
                objective=objective, state=state), [], '已发布的辅导讲解。')
            for card in cards:
                card['memory_epoch'] = epoch
            conversation = self.memory.append_exchange(student, '历史提问', '已发布的辅导讲解。',
                selection_ref={'learning_cards': cards, 'section_title': point or self.point}, session_id=session)
            with session_scope() as db:
                db.get(ConversationRow, conversation).created_at = now

    def items(self, **kwargs):
        return review_followups('s', self.memory.repo, course_id='course-test', **kwargs)

    def test_pending_snapshot_is_private_read_only_and_not_mastery(self):
        self.add()
        before = self.count(LearningEventRow)
        items = self.items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['reason_code'], 'pending_snapshot')
        self.assertEqual(items[0]['location_label'], '第2章 · 第2节（上次学习位置）')
        self.assertFalse(items[0]['mastery_credit'])
        self.assertTrue(items[0]['requires_retrieval'])
        self.assertEqual(items[0]['evidence_status'], 'formative_unverified')
        self.assertNotIn('PRIVATE-', json.dumps(items))
        self.assertNotIn('due_at', items[0])
        self.assertEqual(self.items(), items)
        self.assertEqual(self.count(LearningEventRow), before)

    def test_latest_snapshot_can_remove_older_pending_without_awarding_mastery(self):
        self.add(age=10)
        self.add(self.state(pending=False, verdict='correct'))
        self.assertEqual(self.items(), [])

    def test_partial_feedback_is_only_a_suggestion(self):
        self.add(self.state(pending=False, verdict='partial'))
        item = self.items()[0]
        self.assertEqual(item['reason_code'], 'provisional_feedback')
        self.assertIn('不是正式评分', item['reason'])
        self.assertNotIn('mastery', item)

    def test_support_request_can_be_followed_up_without_scoring(self):
        state = self.state(pending=False)
        state['turn_move'] = 'needs_support'
        self.add(state)
        self.assertEqual(self.items()[0]['reason_code'], 'requested_support')

    def test_student_course_failed_and_uncommitted_scopes_are_excluded(self):
        self.add(student='other')
        foreign = self.state();foreign['progress']['book_id'] = 'another-course'
        self.add(foreign)
        self.add(committed=False)
        self.add(status='failed')
        self.assertEqual(self.items(), [])

    def test_old_epoch_and_deleted_point_cannot_reappear(self):
        self.add(epoch=1)
        self.assertEqual(self.items(), [])
        self.add(epoch=0)
        self.assertEqual(len(self.items()), 1)
        self.memory.forget_point('s', self.point)
        self.assertEqual(self.items(), [])

    def test_expired_task_is_historical_suggestion_not_an_active_question(self):
        self.add(age=7200)
        LearningTaskRepository().expire('s', 'tab-a')
        item = self.items()[0]
        self.assertIn('上次', item['reason'])
        self.assertNotIn('pending_question', item)
        self.assertTrue(item['requires_retrieval'])

    def test_sessions_remain_separate_and_results_are_bounded(self):
        self.add(session='tab-a', age=10)
        self.add(session='tab-b')
        items = self.items()
        self.assertEqual(len(items), 2)
        self.assertNotEqual(items[0]['followup_id'], items[1]['followup_id'])
        self.assertEqual(len(self.items(limit=1)), 1)

    def test_malformed_legacy_snapshot_does_not_break_review_list(self):
        self.add()
        with session_scope() as db:
            row = db.scalar(select(ConversationRow).where(ConversationRow.student_id == 's', ConversationRow.role == 'assistant'))
            db.get(PDFCitationRow, row.id).reference = {'learning_cards': ['legacy-data']}
        self.assertEqual(self.items(), [])

    def test_review_does_not_validate_or_rescan_entire_textbook(self):
        self.add()
        with patch('knowledge.course_release.validate', side_effect=AssertionError('full-book scan')):
            self.assertEqual(len(self.items()), 1)

    def test_existing_review_api_includes_followup_and_does_not_change_state(self):
        from web_api import router
        self.add()
        app = FastAPI(); app.include_router(router)
        before = self.count(LearningEventRow)
        with patch('practice_api.catalog', return_value={'version': 'v', 'by_id': {}}), \
             patch('knowledge.course_config.COURSE_ID', 'course-test'), TestClient(app) as client:
            result = client.get('/api/students/s/review')
        self.assertEqual(result.status_code, 200)
        self.assertEqual([item['kind'] for item in result.json()], ['learning_followup'])
        self.assertFalse(result.json()[0]['mastery_credit'])
        self.assertEqual(self.count(LearningEventRow), before)

    def test_existing_weak_point_is_not_duplicated_by_historical_suggestion(self):
        from web_api import router
        self.add()
        state = self.memory.get_state('s', self.point)
        state.turn_count = 1
        self.memory.save_state('s', self.point, state)
        app = FastAPI(); app.include_router(router)
        with patch('practice_api.catalog', return_value={'version': 'v', 'by_id': {}}), \
             patch('knowledge.course_config.COURSE_ID', 'course-test'), TestClient(app) as client:
            items = client.get('/api/students/s/review').json()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['kind'], 'low_mastery')

    def test_correction_removes_label_but_preserves_neutral_followup_until_point_deleted(self):
        from agents.adaptive_tutoring import snapshot_from_recent
        from models.task_context import TaskContext
        from web_api import router
        self.add()
        target = self.memory.add_hypothesis('s', self.point, 'set_element_confusion', '旧误解判断', .9)
        app = FastAPI(); app.include_router(router)
        with patch('practice_api.catalog', return_value={'version': 'v', 'by_id': {}}), \
             patch('knowledge.course_config.COURSE_ID', 'course-test'), TestClient(app) as client:
            before = client.get('/api/students/s/review').json()
            self.assertEqual([item['kind'] for item in before], ['misconception'])
            self.memory.dispute_misconception('s', target.id, '这项判断不符合我的情况')
            after = client.get('/api/students/s/review').json()
            self.assertEqual([item['kind'] for item in after], ['learning_followup'])
            self.assertFalse(after[0]['mastery_credit'])
            self.assertNotIn('旧误解判断', json.dumps(after, ensure_ascii=False))
            self.memory.forget_point('s', self.point)
            self.assertEqual(client.get('/api/students/s/review').json(), [])
        old = {'student_id': 's', 'session_id': 'tab-a', 'knowledge_point': self.point, 'epoch': 0,
               'result': {'answer_status': 'answered', 'memory_commit': {'status': 'committed'}},
               'context': {'tutoring': self.state()}}
        context = TaskContext(student_id='s', session_id='tab-a', message='继续', knowledge_point=self.point)
        self.assertEqual(snapshot_from_recent([old], context, self.memory.repo, 's'), {})


if __name__ == '__main__':
    unittest.main()
