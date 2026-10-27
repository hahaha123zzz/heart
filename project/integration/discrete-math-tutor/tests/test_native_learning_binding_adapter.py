"""原生switch/leave工具 + 真实SQLite会话/租约交接；不调用真实模型。"""
import asyncio
import unittest
from unittest.mock import patch

from database.database import session_scope
from database.models import MemoryControlRow
from integrations.deeptutor.client import BackendUnavailable
from integrations.deeptutor.native_contract import NativeTurnStart, NativeTurnCommand
from tests import test_native_learning_authorization as authority_fixtures
from tests import test_deeptutor_native_runtime as native_fixtures


class NativeBindingAdapterTests(unittest.IsolatedAsyncioTestCase):
    finished = native_fixtures.NativeRuntimeTests.finished
    _collect = native_fixtures.NativeRuntimeTests._collect

    async def asyncSetUp(self):
        await native_fixtures.NativeRuntimeTests.asyncSetUp(self)
        self.host = authority_fixtures.HostNativeAuthorizationTests(methodName='test_authorizes_real_task_without_sending_student_content')
        self.host.setUp()
        self.post = patch('integrations.deeptutor.client.DeepTutorBackend._post', side_effect=self.host_post)
        self.post.start()
        self.request = NativeTurnStart(**self.host.payload, course_title='路径交接隔离课程', content='block')
        await self.bridge.start(self.request)
        await asyncio.wait_for(self.started.wait(), 10)
        self.entry = self.bridge.entry(self.request)
        from deeptutor.learning.models import LearningProgress
        from deeptutor.learning.storage import LearningStore
        from deeptutor.services.session import get_session_store
        with self.bridge.scope(self.entry):
            store = LearningStore()
            for path in ('path-a', 'path-b'):
                store.save(LearningProgress(book_id=path, name=path))
            store.acquire_path_lease('path-a', self.entry['native_session_id'], self.entry['turn_id'])
            await get_session_store().update_session_preferences(self.entry['native_session_id'], {'mastery_path_id': 'path-a', 'keep_me': True})

    async def asyncTearDown(self):
        from deeptutor.services.session import get_session_store
        with self.bridge.scope(self.entry):
            with get_session_store()._connect() as conn:
                conn.execute('DROP TRIGGER IF EXISTS reject_handoff')
                conn.commit()
        await self.bridge.command(native_fixtures.key(self.request, NativeTurnCommand, command_id='cleanup'))
        await self.finished(self.request)
        self.post.stop()
        self.host.tearDown()
        await native_fixtures.NativeRuntimeTests.asyncTearDown(self)

    def host_post(self, path, payload):
        response = self.host.client.post(path, json=payload, headers={'X-Heart-Bridge-Token': 't' * 32})
        if response.status_code != 200:
            raise BackendUnavailable('宿主拒绝旧epoch')
        return response.json()

    async def state(self):
        from deeptutor.learning.storage import LearningStore
        from deeptutor.services.session import get_session_store
        with self.bridge.scope(self.entry):
            store = LearningStore()
            session = await get_session_store().get_session(self.entry['native_session_id'])
            return {'path': store.path_id_for_session(self.entry['native_session_id']), 'preferences': session['preferences'],
                'leases': {path: lease.model_dump() if lease else None for path in ('path-a', 'path-b', self.entry['native_session_id'])
                           for lease in [store.get_path_lease(path)]}}

    def kwargs(self):
        return {'_session_id': self.entry['native_session_id'], '_turn_id': self.entry['turn_id'],
                '_mastery_path_id': 'path-a'}

    async def test_original_switch_updates_binding_lease_preferences_and_live_turn(self):
        from deeptutor.capabilities.mastery.tools import MasterySwitchTool
        changed = []
        with self.bridge.scope(self.entry):
            result = await MasterySwitchTool().execute(path_id='path-b', **self.kwargs(), _bind_active_path=changed.append)
        self.assertTrue(result.success)
        state = await self.state()
        self.assertEqual(state['path'], 'path-b')
        self.assertEqual(state['preferences']['mastery_path_id'], 'path-b')
        self.assertTrue(state['preferences']['keep_me'])
        self.assertIsNone(state['leases']['path-a'])
        self.assertEqual(state['leases']['path-b']['turn_id'], self.entry['turn_id'])
        self.assertEqual(changed, ['path-b'])

    async def test_busy_target_preserves_original_position_and_lease(self):
        from deeptutor.capabilities.mastery.tools import MasterySwitchTool
        from deeptutor.learning.storage import LearningStore
        with self.bridge.scope(self.entry):
            LearningStore().acquire_path_lease('path-b', 'other-session', 'other-turn')
        before = await self.state()
        with self.bridge.scope(self.entry):
            result = await MasterySwitchTool().execute(path_id='path-b', **self.kwargs())
        self.assertFalse(result.success)
        self.assertEqual(await self.state(), before)

    async def test_session_write_failure_rolls_back_learning_binding_and_lease(self):
        from deeptutor.capabilities.mastery.tools import MasterySwitchTool
        from deeptutor.services.session import get_session_store
        before = await self.state()
        with self.bridge.scope(self.entry):
            with get_session_store()._connect() as conn:
                conn.execute("CREATE TRIGGER reject_handoff BEFORE UPDATE OF preferences_json ON sessions BEGIN SELECT RAISE(ABORT,'injected failure'); END")
                conn.commit()
            result = await MasterySwitchTool().execute(path_id='path-b', **self.kwargs())
        self.assertFalse(result.success)
        self.assertEqual(await self.state(), before)

    async def test_revocation_before_commit_rolls_back_both_databases(self):
        from deeptutor.capabilities.mastery.tools import MasterySwitchTool
        from deeptutor.services.session.workspace_preferences import upgrade_workspace_preferences
        before = await self.state()
        def revoke(preferences):
            with session_scope() as db:
                db.add(MemoryControlRow(student_id='s', knowledge_point='变量', epoch=1))
            return upgrade_workspace_preferences(preferences)
        with self.bridge.scope(self.entry), patch('deeptutor.services.session.workspace_preferences.upgrade_workspace_preferences', side_effect=revoke):
            with self.assertRaises(BackendUnavailable):
                await MasterySwitchTool().execute(path_id='path-b', **self.kwargs())
        self.assertEqual(await self.state(), before)

    async def test_leave_uses_owned_scratch_and_preserves_named_path(self):
        from deeptutor.capabilities.mastery.tools import MasteryLeaveTool
        from deeptutor.learning.storage import LearningStore
        with self.bridge.scope(self.entry):
            result = await MasteryLeaveTool().execute(**self.kwargs())
        self.assertTrue(result.success)
        state = await self.state()
        self.assertEqual(state['path'], self.entry['native_session_id'])
        self.assertEqual(state['preferences']['mastery_path_id'], '')
        self.assertIsNone(state['leases']['path-a'])
        with self.bridge.scope(self.entry):
            store = LearningStore()
            self.assertEqual(store.load('path-a').name, 'path-a')
            self.assertFalse(store.load(state['path']).mastery_levels)
            with store._connect() as conn:
                owner = conn.execute('SELECT owner_session_id FROM mastery_paths WHERE path_id=?', (state['path'],)).fetchone()[0]
            self.assertEqual(owner, self.entry['native_session_id'])

    async def test_spoofed_session_or_turn_cannot_change_position(self):
        from deeptutor.capabilities.mastery.tools import MasterySwitchTool
        before = await self.state()
        for key in ('_session_id', '_turn_id'):
            with self.subTest(key=key), self.bridge.scope(self.entry):
                result = await MasterySwitchTool().execute(path_id='path-b', **(self.kwargs() | {key: 'other'}))
                self.assertFalse(result.success)
        self.assertEqual(await self.state(), before)

    async def test_missing_context_and_archived_or_unknown_target_fail_closed(self):
        from deeptutor.capabilities.mastery.tools import MasterySwitchTool
        from deeptutor.learning.models import TopicMetadata
        from deeptutor.learning.storage import LearningStore
        from deeptutor.services.workspace.context import workspace_context
        before = await self.state()
        with self.bridge.user_scope(self.entry['user_id']), workspace_context(self.entry['workspace_id']):
            with self.assertRaises(BackendUnavailable):
                await MasterySwitchTool().execute(path_id='path-b', **self.kwargs())
        with self.bridge.scope(self.entry):
            LearningStore().put_topic(TopicMetadata(path_id='path-b', status='archived'), [])
            for target in ('path-b', 'unknown-path'):
                with self.subTest(target=target):
                    result = await MasterySwitchTool().execute(path_id=target, **self.kwargs())
                    self.assertFalse(result.success)
        self.assertEqual(await self.state(), before)

    async def test_live_callback_failure_reports_saved_position_instead_of_claiming_rollback(self):
        from deeptutor.capabilities.mastery.tools import MasterySwitchTool
        def fail_callback(target):
            raise RuntimeError('injected live callback failure')
        with self.bridge.scope(self.entry):
            result = await MasterySwitchTool().execute(path_id='path-b', **self.kwargs(), _bind_active_path=fail_callback)
        self.assertFalse(result.success)
        self.assertIn('位置已保存', result.content)
        state = await self.state()
        self.assertEqual(state['path'], 'path-b')
        self.assertEqual(state['preferences']['mastery_path_id'], 'path-b')
        self.assertIsNone(state['leases']['path-a'])


if __name__ == '__main__':
    unittest.main()
