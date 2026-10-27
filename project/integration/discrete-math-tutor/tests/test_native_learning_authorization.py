"""真实宿主SQLite授权接口与原生回合阻断；不调用真实模型。"""
import os
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from database.database import session_scope
from database.learning_tasks import LearningTaskRepository
from database.models import LearningTaskRow, MemoryControlRow, Student
from database.repository import Repository
from integrations.deeptutor.native_authorization import router
from integrations.deeptutor.native_bridge import NativeTurnBridge
from integrations.deeptutor.native_contract import NativeTaskCheck, NativeTurnStart, NativeTurnReply, NativeTurnCommand, NativeTurnCursor
from tests import test_q5_learning as host_fixtures
from tests import test_deeptutor_native_runtime as native_fixtures

original_authorize = NativeTurnBridge.authorize_host


class HostNativeAuthorizationTests(unittest.TestCase):
    def setUp(self):
        host_fixtures.Q5TestBase.setUp(self)
        self.env = patch.dict(os.environ, DEEPTUTOR_BRIDGE_TOKEN='t' * 32)
        self.env.start()
        self.course = patch('integrations.deeptutor.native_authorization.COURSE_ID', 'course-1')
        self.course.start()
        self.documents = patch('knowledge.pdf_reader.documents', return_value=[{'document_id': 'doc', 'version': 'v1'}])
        self.documents_mock = self.documents.start()
        row, _, _ = LearningTaskRepository().claim(student_id='s', session_id='sess', request_id='r1',
            payload={'message': 'private text'}, point='变量', epoch=0, memory_repo=Repository())
        with session_scope() as db:
            db.get(LearningTaskRow, row['id']).context = {'document_versions': {'doc': 'v1'}}
        self.payload = NativeTaskCheck(student_id='s', session_id='sess', course_id='course-1',
            request_id='r1', task_id=row['id'], task_revision=row['revision'], memory_epoch=0,
            material_versions={'doc': 'v1'}).model_dump()
        app = FastAPI(); app.include_router(router)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.documents.stop(); self.course.stop(); self.env.stop()
        host_fixtures.Q5TestBase.tearDown(self)

    def check(self, **changes):
        return self.client.post('/internal/heart/native/authorize', headers={'X-Heart-Bridge-Token': 't' * 32},
                                json=self.payload | changes)

    def test_authorizes_real_task_without_sending_student_content(self):
        response = self.check()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'authorized': True, **self.payload})
        self.assertNotIn('private text', response.text)
        self.assertEqual(self.client.post('/internal/heart/native/authorize', json=self.payload).status_code, 401)
        self.assertEqual(self.check(user_id='admin').status_code, 422)

    def test_wrong_student_session_course_request_revision_and_epoch_are_rejected(self):
        for key, value in (('student_id', 'other'), ('session_id', 'other'), ('course_id', 'other'),
                           ('request_id', 'other'), ('task_revision', 99), ('memory_epoch', 99)):
            with self.subTest(key=key):
                self.assertEqual(self.check(**{key: value}).status_code, 409)

    def test_deleted_memory_rejects_the_original_epoch(self):
        with session_scope() as db:
            db.add(MemoryControlRow(student_id='s', knowledge_point='变量', epoch=1))
        response = self.check()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['detail']['code'], 'memory_deleted')

    def test_deleted_student_and_cancelled_task_are_rejected(self):
        with session_scope() as db:
            db.get(LearningTaskRow, self.payload['task_id']).status = 'cancelled'
        self.assertEqual(self.check().status_code, 409)
        with session_scope() as db:
            db.get(LearningTaskRow, self.payload['task_id']).status = 'executing'
            db.delete(db.get(Student, 's'))
        self.assertEqual(self.check().status_code, 409)

    def test_changed_or_omitted_material_snapshot_is_rejected(self):
        self.assertEqual(self.check(material_versions={}).status_code, 409)
        self.documents_mock.return_value = [{'document_id': 'doc', 'version': 'v2'}]
        self.assertEqual(self.check().status_code, 409)


class NativeAuthorizationBoundaryTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = native_fixtures.NativeRuntimeTests.asyncSetUp
    asyncTearDown = native_fixtures.NativeRuntimeTests.asyncTearDown
    finished = native_fixtures.NativeRuntimeTests.finished
    _collect = native_fixtures.NativeRuntimeTests._collect

    async def test_default_callback_fails_closed_and_checks_response_identity(self):
        request = native_fixtures.request()
        from integrations.deeptutor.client import BackendUnavailable
        with patch('integrations.deeptutor.client.DeepTutorBackend._post', side_effect=BackendUnavailable('offline')):
            with self.assertRaises(HTTPException):
                await original_authorize(self.bridge, request)
        expected = request.model_dump(include=set(NativeTaskCheck.model_fields))
        with patch('integrations.deeptutor.client.DeepTutorBackend._post', return_value={'authorized': True, **expected}):
            await original_authorize(self.bridge, request)
        with patch('integrations.deeptutor.client.DeepTutorBackend._post', return_value={'authorized': True, **expected, 'task_revision': 99}):
            with self.assertRaises(HTTPException):
                await original_authorize(self.bridge, request)

    async def test_revoked_authority_prevents_start_before_account_or_model(self):
        with patch.object(self.bridge, 'authorize_host', new=AsyncMock(side_effect=HTTPException(409, 'deleted'))):
            with self.assertRaises(HTTPException):
                await self.bridge.start(native_fixtures.request())
        self.assertEqual(self.calls, [])
        with self.sessions._connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM native_requests').fetchone()[0], 0)

    async def test_revocation_blocks_replay_events_and_reply_but_keeps_cancellation(self):
        request = native_fixtures.request()
        await self.bridge.start(request); await self.finished(request)
        with patch.object(self.bridge, 'authorize_host', new=AsyncMock(side_effect=HTTPException(409, 'deleted'))):
            with self.assertRaises(HTTPException):
                await self.bridge.status(request)
            with self.assertRaises(HTTPException):
                await self.bridge.start(request)
            with self.assertRaises(HTTPException):
                await self.bridge.command(native_fixtures.key(request, NativeTurnReply, command_id='reply1', text='旧答复'))
            with self.assertRaises(HTTPException):
                await self.finished(request)
            await self.bridge.command(native_fixtures.key(request, NativeTurnCommand, command_id='cancel1'))
        self.assertEqual(len(self.calls), 1)

    async def test_deletion_during_replay_does_not_release_done(self):
        request = native_fixtures.request()
        await self.bridge.start(request); await self.finished(request)
        count = 0
        async def revoke_after_open(*args):
            nonlocal count
            count += 1
            if count > 1:
                raise HTTPException(409, 'deleted')
        events = []
        with patch.object(self.bridge, 'authorize_host', side_effect=revoke_after_open):
            with self.assertRaises(HTTPException):
                async for event in self.bridge.events(native_fixtures.key(request, NativeTurnCursor)):
                    events.append(event)
        self.assertTrue(all(item['event']['type'] != 'done' for item in events))

    async def test_real_host_sqlite_callback_and_native_app_reject_deleted_epoch(self):
        from integrations.deeptutor.client import BackendUnavailable
        host = HostNativeAuthorizationTests(methodName='test_authorizes_real_task_without_sending_student_content')
        host.setUp()
        def post(path, payload):
            self.assertEqual(path, '/internal/heart/native/authorize')
            response = host.client.post(path, json=payload, headers={'X-Heart-Bridge-Token': 't' * 32})
            if response.status_code != 200:
                raise BackendUnavailable('host rejected')
            return response.json()
        try:
            request = NativeTurnStart(**host.payload, course_title='隔离课程', content='解释自变量')
            with patch.object(self.bridge, 'authorize_host', new=original_authorize.__get__(self.bridge)), \
                 patch('integrations.deeptutor.client.DeepTutorBackend._post', side_effect=post):
                await self.bridge.start(request)
                events = await self.finished(request)
                self.assertTrue(any(item['event']['type'] == 'done' for item in events))
                with self.bridge.learning_service(request) as service:
                    self.assertEqual(service.get_or_create('guarded-probe').book_id, 'guarded-probe')
                    self.assertTrue(service._store.db_path.resolve().is_relative_to(self.home.resolve()))
                with session_scope() as db:
                    db.add(MemoryControlRow(student_id='s', knowledge_point='变量', epoch=1))
                with self.assertRaises(HTTPException):
                    await self.bridge.status(request)
                with self.assertRaises(HTTPException):
                    await self.bridge.start(request)
                with self.assertRaises(BackendUnavailable):
                    with self.bridge.learning_service(request):
                        self.fail('旧epoch不应获得学习写入服务')
                self.assertEqual(len(self.calls), 1)
        finally:
            host.tearDown()


if __name__ == '__main__':
    unittest.main()
