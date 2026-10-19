"""真实应用层、上下文、协调器和SQLite；只用受控能力替代模型回答。"""
import asyncio
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from integrations.deeptutor.native_bridge import NativeTurnBridge, install_native_bridge
from integrations.deeptutor.native_contract import NativeTurnKey, NativeTurnStart, NativeTurnCursor, NativeTurnCommand, NativeTurnReply
from integrations.deeptutor.session_bridge import SessionBridge


def request(**changes):
    return NativeTurnStart(**(dict(student_id='student-a', course_id='psychology', session_id='tab-a',
        request_id='request-a', task_id='task-a', task_revision=1, course_title='实验心理学',
        content='解释自变量', memory_epoch=0, material_versions={}) | changes))


def key(value, cls=NativeTurnKey, **changes):
    return cls(**(value.model_dump(include=set(NativeTurnKey.model_fields)) | changes))


class NativeBoundaryTests(unittest.TestCase):
    def test_token_switch_and_server_owned_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            app = FastAPI(); install_native_bridge(app, SessionBridge(Path(directory)))
            with TestClient(app) as client, patch.dict(os.environ, DEEPTUTOR_BRIDGE_TOKEN='t' * 32, DEEPTUTOR_NATIVE_ENABLED='0'):
                payload = request().model_dump()
                self.assertEqual(client.post('/internal/heart/native/start', json=payload).status_code, 401)
                headers = {'X-Heart-Bridge-Token': 't' * 32}
                self.assertEqual(client.post('/internal/heart/native/start', headers=headers, json=payload).status_code, 503)
                with patch.dict(os.environ, DEEPTUTOR_NATIVE_ENABLED='1'):
                    for extra in ({'user_id': 'admin'}, {'workspace_id': 'other'}, {'api_key': 'private'}, {'tools': ['exec']}, {'capability': 'deep_research'}):
                        self.assertEqual(client.post('/internal/heart/native/start', headers=headers, json=payload | extra).status_code, 422)
                    self.assertEqual(client.post('/internal/heart/native/status', headers=headers, json=key(request()).model_dump()).status_code, 404)


class NativeRuntimeTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        if importlib.util.find_spec('deeptutor') is None: raise unittest.SkipTest('需要固定上游环境')

    async def asyncSetUp(self):
        from deeptutor.app.container import ApplicationContainer
        from deeptutor.core.capability_protocol import CapabilityManifest, TurnCapability
        from deeptutor.core.stream import StreamEvent, StreamEventType
        from deeptutor.multi_user.context import get_current_user
        from deeptutor.runtime.capability_catalog import CapabilityCatalog
        from deeptutor.runtime.coordination import CoordinationSettings, MemoryCoordinator
        from deeptutor.runtime.registry.capability_registry import CapabilityRegistry
        from deeptutor.services.path_service import PathService
        from deeptutor.services.llm.config import get_llm_config
        from deeptutor.services.session.turns.title_service import SessionTitleService
        from deeptutor.services.workspace.context import current_workspace_id

        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.env = patch.dict(os.environ, DEEPTUTOR_HOME=str(self.home), DEEPSEEK_API_KEY='fixture-key', DEEPSEEK_MODEL='fixture-model')
        self.env.start()
        from deeptutor.multi_user import paths, identity, grants
        self.storage_patches = [
            patch.object(paths, 'ADMIN_WORKSPACE_ROOT', self.home / 'data'),
            patch.object(paths, 'USERS_ROOT', self.home / 'data/users'),
            patch.object(paths, 'SYSTEM_ROOT', self.home / 'data/system'),
            patch.object(paths, '_legacy_migration_done', True),
            patch.object(identity, 'USERS_FILE', self.home / 'data/system/auth/users.json'),
            patch.object(identity, 'LEGACY_USERS_FILE', self.home / 'no-legacy-users.json'),
            patch.object(grants, 'GRANTS_DIR', self.home / 'data/system/grants'),
        ]
        for guard in self.storage_patches: guard.start()
        self.path_patch = patch.object(PathService, '_instance', PathService(workspace_root=self.home / 'data'))
        self.path_patch.start()
        self.calls, self.replies = [], []
        self.started, self.cancelled = asyncio.Event(), asyncio.Event()
        owner = self

        class ControlledChat(TurnCapability):
            manifest = CapabilityManifest(name='chat', description='受控协议验证')
            async def run(self, context, stream):
                owner.assertFalse(get_current_user().is_admin)
                owner.assertEqual(get_llm_config().model, 'fixture-model')
                owner.calls.append({'content': context.user_message, 'user': get_current_user().id,
                    'workspace': current_workspace_id(), 'history': context.conversation_history})
                if context.user_message == 'fail': raise RuntimeError('controlled failure')
                if context.user_message == 'block':
                    owner.started.set()
                    try: await asyncio.Event().wait()
                    finally: owner.cancelled.set()
                text = context.user_message
                if context.active_capability == 'ask_questions':
                    await stream.emit(StreamEvent(type=StreamEventType.WAIT_FOR_INPUT, source='chat',
                        metadata={'questions': [{'id': 'target', 'question': '你指哪两个对象？'}]}))
                    reply = await context.runtime.wait_for_user_reply()
                    owner.replies.append(reply)
                    text += '→' + reply['text']
                await stream.emit(StreamEvent(type=StreamEventType.CONTENT, source='chat',
                    content='回答：' + text, metadata={'call_kind': 'llm_final_response'}))

        class ControlledQuestions(ControlledChat):
            manifest = CapabilityManifest(name='ask_questions', description='受控澄清验证')

        self.container = ApplicationContainer(settings=CoordinationSettings(), coordinator=MemoryCoordinator(), worker_id='native-test-worker')
        registry = CapabilityRegistry(CapabilityCatalog())
        registry.register(ControlledChat); registry.register(ControlledQuestions)
        self.container.capability_registry = registry
        self.container.turn_engine.capability_registry = registry
        self.app_patch = patch('deeptutor.app.facade.get_application_container', return_value=self.container)
        self.app_patch.start()
        self.title_patch = patch.object(SessionTitleService, '_maybe_generate_session_title', new_callable=AsyncMock)
        self.title_patch.start()
        self.network_patch = patch('deeptutor.services.llm.provider_factory.build_isolated_provider', side_effect=AssertionError('本测试禁止联网模型'))
        self.network_patch.start()
        self.sessions = SessionBridge(self.home)
        self.bridge = NativeTurnBridge(self.sessions)

    async def asyncTearDown(self):
        await self.container.runtime_registry.close(drain_timeout_seconds=1)
        await self.container.close()
        for guard in (self.network_patch, self.title_patch, self.app_patch, self.path_patch, self.env): guard.stop()
        for guard in reversed(self.storage_patches): guard.stop()
        self.temp.cleanup()

    async def finished(self, req):
        return await asyncio.wait_for(self._collect(req), 15)

    async def _collect(self, req):
        return [event async for event in self.bridge.events(key(req, NativeTurnCursor))]

    async def wait_status(self, req, status):
        async def poll():
            while True:
                result = await self.bridge.status(key(req))
                if result['status'] == status: return result
                await asyncio.sleep(.02)
        return await asyncio.wait_for(poll(), 10)

    async def test_real_application_persists_and_replays_without_second_execution(self):
        req = request()
        receipt = await self.bridge.start(req)
        events = await self.finished(req)
        result = await self.bridge.status(key(req))
        replay = await NativeTurnBridge(self.sessions).start(req)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(replay['turn_id'], receipt['turn_id'])
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(all(event['publication_state'] == 'pending_verification' for event in events))
        self.assertTrue(any(event['event']['type'] == 'done' for event in events))
        entry = self.bridge.entry(req)
        with self.bridge.scope(entry) as app:
            messages = await app.container.store_provider.get().get_messages(entry['native_session_id'])
        self.assertEqual([message['role'] for message in messages], ['user', 'assistant'])
        self.assertEqual(messages[-1]['content'], '回答：解释自变量')
        cursor = events[-1]['event']['seq']
        tail = [event async for event in self.bridge.events(key(req, NativeTurnCursor, after_seq=cursor))]
        # 原生订阅在游标已越过 DONE 时仍会发一个 synthesized 终态；不能当新执行。
        self.assertTrue(all(item['event']['type'] == 'done' and item['event']['metadata']['synthesized'] for item in tail))

    async def test_receipt_gap_recovers_durable_submission(self):
        req = request(); first = await self.bridge.start(req); await self.finished(req)
        with self.sessions._connect() as db:
            db.execute('UPDATE native_requests SET turn_id=NULL')
        recovered = await NativeTurnBridge(self.sessions).start(req)
        self.assertEqual(first['turn_id'], recovered['turn_id'])
        self.assertEqual(len(self.calls), 1)

    async def test_orphaned_active_turn_is_reaped_before_new_execution(self):
        req = request(); await self.bridge.start(req); await self.finished(req)
        with self.bridge.scope(self.bridge.entry(req)) as app:
            store = app.container.store_provider.get()
            await store.begin_turn(self.bridge.entry(req)['native_session_id'], 'chat', turn_id='orphaned-turn')
        following = request(request_id='request-b', task_id='task-b', content='继续解释')
        await self.bridge.start(following); await self.finished(following)
        with self.bridge.scope(self.bridge.entry(req)) as app:
            orphan = await app.container.store_provider.get().get_turn('orphaned-turn')
        self.assertEqual(orphan['status'], 'failed')
        self.assertEqual(orphan['failure_code'], 'worker_lost')
        self.assertEqual(len(self.calls), 2)

    async def test_active_session_conflict_does_not_start_second_execution(self):
        req = request(content='block'); await self.bridge.start(req)
        await asyncio.wait_for(self.started.wait(), 10)
        other = request(request_id='request-b', task_id='task-b')
        with self.assertRaises(HTTPException) as conflict: await self.bridge.start(other)
        self.assertEqual(conflict.exception.status_code, 409)
        self.assertEqual(len(self.calls), 1)
        await self.bridge.command(key(req, NativeTurnCommand, command_id='cancel-1'))
        await self.wait_status(req, 'cancelled'); await self.finished(req)
        self.assertEqual((await self.bridge.start(req))['status'], 'cancelled')
        self.assertEqual(len(self.calls), 1)

    async def test_native_context_builder_receives_prior_turn(self):
        first = request(); await self.bridge.start(first); await self.finished(first)
        second = request(request_id='request-b', task_id='task-b', content='换简单说法')
        await self.bridge.start(second); await self.finished(second)
        self.assertTrue(any('解释自变量' in str(message.get('content')) for message in self.calls[-1]['history']))

    async def test_scope_digest_and_resource_changes_are_rejected(self):
        req = request(); await self.bridge.start(req); await self.finished(req)
        for changes in ({'student_id': 'student-b'}, {'course_id': 'other'}, {'session_id': 'other'}, {'request_id': 'other'}):
            with self.assertRaises(HTTPException) as failure: await self.bridge.status(key(req).model_copy(update=changes))
            self.assertEqual(failure.exception.status_code, 404)
        for changes in ({'task_revision': 2}, {'content': 'changed'}, {'memory_epoch': 1}, {'material_versions': {'book': 'new'}}):
            with self.assertRaises(HTTPException) as failure: await self.bridge.start(req.model_copy(update=changes))
            self.assertEqual(failure.exception.status_code, 409)
        self.assertEqual(len(self.calls), 1)

    async def test_two_students_and_two_courses_have_distinct_workspaces(self):
        requests = [request(), request(student_id='student-b'), request(course_id='other-course')]
        receipts = await asyncio.gather(*(self.bridge.start(req) for req in requests))
        await asyncio.gather(*(self.finished(req) for req in requests))
        self.assertEqual(len({receipt['workspace_id'] for receipt in receipts}), 3)
        self.assertEqual(len({receipt['session_id'] for receipt in receipts}), 3)
        self.assertEqual(len({call['user'] for call in self.calls}), 2)

    async def test_user_reply_resumes_same_turn_and_commands_are_deduplicated(self):
        req = request(capability='ask_questions')
        receipt = await self.bridge.start(req)
        await self.wait_status(req, 'waiting_input')
        reply = key(req, NativeTurnReply, command_id='reply-1', text='被试间与被试内')
        first, duplicate = await asyncio.gather(self.bridge.command(reply), self.bridge.command(reply))
        self.assertTrue(first['accepted'] and duplicate['accepted'])
        await self.finished(req)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(self.replies), 1)
        self.assertEqual((await self.bridge.status(req))['turn_id'], receipt['turn_id'])

    async def test_cancel_reaches_running_execution(self):
        req = request(content='block'); await self.bridge.start(req)
        await asyncio.wait_for(self.started.wait(), 10)
        command = key(req, NativeTurnCommand, command_id='cancel-1')
        self.assertTrue((await self.bridge.command(command))['accepted'])
        await self.wait_status(req, 'cancelled')
        self.assertTrue(self.cancelled.is_set())
        await self.finished(req)

    async def test_failed_submission_replay_does_not_regenerate(self):
        req = request(content='fail'); first = await self.bridge.start(req); await self.finished(req)
        retry = await self.bridge.start(req)
        self.assertEqual(retry['status'], 'failed')
        self.assertEqual(retry['turn_id'], first['turn_id'])
        self.assertEqual(len(self.calls), 1)
