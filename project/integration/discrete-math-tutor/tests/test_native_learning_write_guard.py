"""真实宿主epoch + 原生SQLite事务；拒绝提交时路径/事件/证据一起回滚。"""
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from deeptutor.learning.models import KnowledgePoint, LearningModule, LearningProgress, PendingQuestion
from deeptutor.learning.service import LearningService
from deeptutor.learning.storage import LearningStore
from database.database import session_scope
from database.models import MemoryControlRow
from integrations.deeptutor.client import BackendUnavailable
from integrations.deeptutor.learning_write_guard import HostAuthorizedLearningStore
from integrations.deeptutor.native_contract import NativeTaskCheck
from tests import test_native_learning_authorization as authority_fixtures


class NativeLearningWriteGuardTests(unittest.TestCase):
    def setUp(self):
        self.host = authority_fixtures.HostNativeAuthorizationTests(methodName='test_authorizes_real_task_without_sending_student_content')
        self.host.setUp()
        self.post = patch('integrations.deeptutor.client.DeepTutorBackend._post', side_effect=self.host_post)
        self.post.start()
        self.root = Path(self.host.temp.name) / 'native-learning'
        self.check = NativeTaskCheck(**self.host.payload)
        self.store = HostAuthorizedLearningStore(self.check, root=self.root)
        self.store.save(LearningProgress(book_id='path1', name='原名称', modules=[
            LearningModule(id='m1', name='变量', order=0, knowledge_points=[
                KnowledgePoint(id='point1', name='自变量', type='memory', module_id='m1')])]))

    def tearDown(self):
        self.post.stop()
        self.host.tearDown()

    def host_post(self, path, payload):
        response = self.host.client.post(path, json=payload, headers={'X-Heart-Bridge-Token': 't' * 32})
        if response.status_code != 200:
            raise BackendUnavailable('宿主拒绝旧epoch')
        return response.json()

    def revoke(self):
        with session_scope() as db:
            db.add(MemoryControlRow(student_id='s', knowledge_point='变量', epoch=1))

    def test_original_service_uses_guarded_store_and_does_not_create_mastery(self):
        service = LearningService(self.store)
        self.assertEqual(service.get_or_create('path1').name, '原名称')
        with self.store.transaction('path1') as tx:
            tx.progress.name = '已修改'
            tx.touch()
        progress = self.store.load('path1')
        self.assertEqual(progress.name, '已修改')
        self.assertFalse(progress.mastery_levels)
        self.assertEqual(self.store.count_learning_evidence('path1'), 0)

    def test_revocation_inside_transaction_rolls_back_path_and_events(self):
        before = self.store.load('path1')
        events = len(self.store.list_events('path1'))
        with self.assertRaises(BackendUnavailable):
            with self.store.transaction('path1') as tx:
                tx.progress.name = '不应保存'
                tx.emit('host.test_rejected', {'result': 'must_rollback'})
                self.revoke()
        original = LearningStore(root=self.root)
        after = original.load('path1')
        self.assertEqual((after.name, after.version), (before.name, before.version))
        self.assertEqual(len(original.list_events('path1')), events)
        self.assertEqual(original.count_learning_evidence('path1'), 0)

    def test_revoked_store_blocks_read_save_and_autocommit_reading_activity(self):
        progress = self.store.load('path1')
        self.revoke()
        for action in (lambda: self.store.load('path1'), lambda: self.store.save(progress),
                       lambda: self.store.record_reading_activity('material', extension_id='quiz',
                           action='generate', locator=1, result_type='quiz')):
            with self.subTest(action=action), self.assertRaises(BackendUnavailable):
                action()
        original = LearningStore(root=self.root)
        self.assertEqual(original.list_reading_records().activities, [])

    def test_repeated_commit_on_same_connection_cannot_reuse_cached_authorization(self):
        with self.store._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute("UPDATE mastery_paths SET updated_at=updated_at WHERE path_id='path1'")
            conn.commit()
            conn.execute('BEGIN IMMEDIATE')
            conn.execute("UPDATE mastery_paths SET updated_at=updated_at WHERE path_id='path1'")
            self.revoke()
            with self.assertRaises(sqlite3.DatabaseError):
                conn.commit()
            conn.rollback()

    def test_expected_identity_is_copied_and_cannot_be_changed_by_the_caller(self):
        self.check.memory_epoch = 999
        self.assertEqual(self.store.load('path1').name, '原名称')

    def test_revocation_after_grading_rolls_back_interaction_attempt_evidence_and_review(self):
        service = LearningService(self.store)
        pending = PendingQuestion(question_id='question1', knowledge_point_id='point1', module_id='m1',
                                  prompt='哪个变量由研究者操纵？', expected_answer='自变量')
        service.register_question('path1', pending)
        before = self.store.load('path1')
        original_grade = service._apply_grade
        def grade_then_revoke(*args, **kwargs):
            result = original_grade(*args, **kwargs)
            self.revoke()
            return result
        with patch.object(service, '_apply_grade', side_effect=grade_then_revoke):
            with self.assertRaises(BackendUnavailable):
                service.grade_interaction('path1', answer='自变量', question_id='question1')
        original = LearningStore(root=self.root)
        progress = original.load('path1')
        self.assertEqual(progress.version, before.version)
        self.assertEqual(progress.pending_question.question_id, 'question1')
        self.assertEqual(original.get_interaction('path1', 'question1').status.value, 'registered')
        self.assertEqual(progress.quiz_attempts, [])
        self.assertEqual(progress.mastery_levels, {})
        self.assertEqual(original.count_learning_evidence('path1'), 0)
        self.assertEqual(progress.review_queue, [])

    def test_autocommit_write_after_connection_open_is_also_rejected(self):
        with self.store._connect() as conn:
            self.revoke()
            with self.assertRaises(sqlite3.DatabaseError):
                conn.execute("INSERT INTO reading_activities(activity_id,material_id,extension_id,action,locator,result_type,created_at) VALUES ('a1','m1','quiz','generate',1,'quiz',0)")
        self.assertEqual(LearningStore(root=self.root).list_reading_records().activities, [])


if __name__ == '__main__':
    unittest.main()
