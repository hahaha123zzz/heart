"""复习使用持久题卡授权；原聊天TTL、取消和删除边界保持严格。"""
import datetime as dt
import unittest

from database.database import session_scope
from database.models import LearningTaskRow, MemoryControlRow, PDFCitationRow
from database.repository import Repository
from integrations.deeptutor.native_contract import NativeTurnKey
from tests.test_native_learning_authorization import HostNativeAuthorizationTests as Fixture


class ReviewAuthorizationTests(unittest.TestCase):
    setUp = Fixture.setUp
    tearDown = Fixture.tearDown

    def publish(self):
        binding = {k: self.payload[k] for k in NativeTurnKey.model_fields}
        binding.update(path_id='path', question_id='question', memory_epoch=0,
                       material_versions=self.payload['material_versions'])
        return Repository().append_conversation('s', 'assistant', '已审核题卡', session_id='sess',
            selection_ref={'section_title': '变量', '_native_assessment': binding, 'learning_cards': []})

    def check(self, **changes):
        return self.client.post('/internal/heart/native/authorize-assessment', json=self.payload | changes,
            headers={'X-Heart-Bridge-Token': 't' * 32})

    def test_archived_card_survives_task_ttl_and_cleanup_without_reopening_chat(self):
        cid = self.publish()
        with session_scope() as db:
            projection = db.get(PDFCitationRow, cid)
            reference = dict(projection.reference)
            binding = dict(reference['_native_assessment']);binding.pop('material_versions')
            projection.reference = {**reference, '_native_assessment': binding}
        self.assertEqual(self.check().status_code, 200)
        with session_scope() as db:
            task = db.get(LearningTaskRow, self.payload['task_id'])
            task.expires_at = dt.datetime(2020, 1, 1)
            task.status = 'expired';task.revision += 1
        self.assertEqual(self.check().status_code, 200)
        self.assertEqual(Fixture.check(self).status_code, 409)
        with session_scope() as db:
            db.delete(db.get(LearningTaskRow, self.payload['task_id']))
        self.assertEqual(self.check().status_code, 200)

    def test_no_projection_cannot_renew_expired_task(self):
        with session_scope() as db:
            db.get(LearningTaskRow, self.payload['task_id']).expires_at = dt.datetime(2020, 1, 1)
        self.assertEqual(self.check().status_code, 409)

    def test_cancel_revision_epoch_and_source_remain_revocable(self):
        self.publish()
        for status, revision in [('cancelled', 1), ('executing', 999)]:
            with session_scope() as db:
                row = db.get(LearningTaskRow, self.payload['task_id']);row.status = status;row.revision = revision
            self.assertEqual(self.check().status_code, 409)
        with session_scope() as db:
            row = db.get(LearningTaskRow, self.payload['task_id']);row.status = 'executing';row.revision = self.payload['task_revision']
        self.assertEqual(self.check(memory_epoch=99).status_code, 409)
        self.assertEqual(self.check(material_versions={}).status_code, 409)
        self.documents_mock.return_value = [{'document_id': 'doc', 'version': 'v2'}]
        self.assertEqual(self.check().status_code, 409)
        self.documents_mock.return_value = [{'document_id': 'doc', 'version': 'v1'}]
        with session_scope() as db:
            db.add(MemoryControlRow(student_id='s', knowledge_point='变量', epoch=1))
        self.assertEqual(self.check().status_code, 409)

    def test_deleted_projection_or_cross_owner_is_not_authorized(self):
        cid = self.publish()
        self.assertEqual(self.check(student_id='other').status_code, 409)
        with session_scope() as db:
            db.get(LearningTaskRow, self.payload['task_id']).expires_at = dt.datetime(2020, 1, 1)
            db.delete(db.get(PDFCitationRow, cid))
        self.assertEqual(self.check().status_code, 409)
