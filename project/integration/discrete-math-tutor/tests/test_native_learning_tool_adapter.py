"""原生工具原实现进入宿主授权存储；不调用模型或正式数据库。"""
import asyncio
from dataclasses import replace
import os
import unittest
from unittest.mock import patch

from database.database import session_scope
from database.models import MemoryControlRow
from integrations.deeptutor.client import BackendUnavailable
from integrations.deeptutor.native_contract import NativeTurnStart
from tests import test_native_learning_authorization as authority_fixtures
from tests import test_deeptutor_native_runtime as native_fixtures


class NativeLearningToolAdapterTests(unittest.IsolatedAsyncioTestCase):
    finished = native_fixtures.NativeRuntimeTests.finished
    _collect = native_fixtures.NativeRuntimeTests._collect

    async def asyncSetUp(self):
        await native_fixtures.NativeRuntimeTests.asyncSetUp(self)
        self.host = authority_fixtures.HostNativeAuthorizationTests(methodName='test_authorizes_real_task_without_sending_student_content')
        self.host.setUp()
        self.post = patch('integrations.deeptutor.client.DeepTutorBackend._post', side_effect=self.host_post)
        self.post.start()
        self.request = NativeTurnStart(**self.host.payload, course_title='工具隔离课程', content='解释自变量')
        await self.bridge.start(self.request)
        await self.finished(self.request)
        self.entry = self.bridge.entry(self.request)
        from deeptutor.learning.models import KnowledgePoint, LearningModule, LearningProgress
        from deeptutor.learning.storage import LearningStore
        with self.bridge.scope(self.entry):
            LearningStore().save(LearningProgress(book_id='tool-path', current_module_id='m1', modules=[
                LearningModule(id='m1', name='变量', order=0, knowledge_points=[
                    KnowledgePoint(id='p1', name='自变量', type='concept', module_id='m1')])]))

    async def asyncTearDown(self):
        self.post.stop()
        self.host.tearDown()
        await native_fixtures.NativeRuntimeTests.asyncTearDown(self)

    def host_post(self, path, payload):
        response = self.host.client.post(path, json=payload, headers={'X-Heart-Bridge-Token': 't' * 32})
        if response.status_code != 200:
            raise BackendUnavailable('宿主拒绝旧任务')
        return response.json()

    def revoke(self):
        with session_scope() as db:
            db.add(MemoryControlRow(student_id='s', knowledge_point='变量', epoch=1))

    async def test_original_tool_records_explanation_and_rejects_revoked_epoch(self):
        from deeptutor.capabilities.mastery.tools import MasteryNoteExplainedTool, _new_service
        from deeptutor.learning.storage import LearningStore
        from integrations.deeptutor.learning_write_guard import HostAuthorizedLearningStore
        tool = MasteryNoteExplainedTool()
        kwargs = dict(_mastery_path_id='tool-path', _mastery_session_mode='study',
                      knowledge_point_id='p1', summary='操纵变量的含义')
        with self.bridge.scope(self.entry):
            self.assertIsInstance(_new_service().store, HostAuthorizedLearningStore)
            result = await tool.execute(**kwargs)
            self.assertTrue(result.success)
            progress = LearningStore().load('tool-path')
            self.assertIn('p1', progress.explained_objectives)
            self.assertFalse(progress.mastery_levels)
            before = progress.version
            self.revoke()
            with self.assertRaises(BackendUnavailable):
                await tool.execute(**kwargs)
            self.assertEqual(LearningStore().load('tool-path').version, before)

    async def test_background_task_and_worker_thread_keep_request_scope(self):
        from deeptutor.capabilities.mastery.tools import MasteryNoteExplainedTool, _new_service
        from integrations.deeptutor.learning_write_guard import HostAuthorizedLearningStore
        gate = asyncio.Event()
        async def background():
            await gate.wait()
            service = await asyncio.to_thread(_new_service)
            self.assertIsInstance(service.store, HostAuthorizedLearningStore)
            return await MasteryNoteExplainedTool().execute(_mastery_path_id='tool-path',
                _mastery_session_mode='study', knowledge_point_id='p1', summary='子任务讲解')
        with self.bridge.scope(self.entry):
            task = asyncio.create_task(background())
        gate.set()
        self.assertTrue((await task).success)

    async def test_managed_account_without_scope_is_refused(self):
        from deeptutor.capabilities.mastery.tools import _new_service
        from deeptutor.services.workspace.context import workspace_context
        with self.bridge.user_scope(self.entry['user_id']), workspace_context(self.entry['workspace_id']):
            with self.assertRaises(BackendUnavailable):
                _new_service()
            from deeptutor.multi_user.context import get_current_user
            from deeptutor.multi_user.paths import user_context
            with user_context(replace(get_current_user(), username='renamed-user')):
                with self.assertRaises(BackendUnavailable):
                    _new_service()

    async def test_other_workspace_cannot_use_the_request_context(self):
        from deeptutor.capabilities.mastery.tools import _new_service
        from deeptutor.services.workspace import get_content_workspace_service
        from deeptutor.services.workspace.context import workspace_context
        with self.bridge.scope(self.entry):
            other = get_content_workspace_service().create_workspace('其他教材空间',
                resources={'skills': [], 'mcp': [], 'knowledge_bases': []})
            with workspace_context(other['workspace_id']):
                with self.assertRaises(BackendUnavailable):
                    _new_service()

    async def test_other_account_cannot_use_the_request_context(self):
        from deeptutor.capabilities.mastery.tools import _new_service
        from integrations.deeptutor.session_bridge import SessionBindingRequest
        other = await self.bridge.bind_scope(SessionBindingRequest(student_id='another-student', course_id='course-1',
            course_title='其他课程', session_id='another-tab'))
        with self.bridge.scope(self.entry), self.bridge.user_scope(other['user_id']):
            with self.assertRaises(BackendUnavailable):
                _new_service()

    async def test_factory_install_is_idempotent_and_does_not_replace_global_store(self):
        from deeptutor.capabilities.mastery import tools
        from deeptutor.learning.storage import LearningStore
        from integrations.deeptutor.learning_tool_adapter import install_learning_tool_factory
        from integrations.deeptutor.learning_write_guard import HostAuthorizedLearningStore
        before = tools._new_service
        install_learning_tool_factory()
        self.assertIs(tools._new_service, before)
        self.assertIsNot(LearningStore, HostAuthorizedLearningStore)
        # 非宿主管理的独立原生环境沿用原工厂，测试目录由fixture隔离。
        service = tools._new_service()
        self.assertIs(type(service.store), LearningStore)

    async def test_enabled_bootstrap_restores_managed_ids_from_native_registry(self):
        from integrations.deeptutor import learning_tool_adapter
        from integrations.deeptutor.native_bridge import NativeTurnBridge
        with patch.object(learning_tool_adapter, '_managed_users', set()):
            with patch.dict(os.environ, DEEPTUTOR_NATIVE_ENABLED='1'):
                NativeTurnBridge(self.sessions)
            self.assertIn(self.entry['user_id'], learning_tool_adapter._managed_users)

    async def test_foreign_factory_is_not_silently_overwritten(self):
        from deeptutor.capabilities.mastery import tools
        from integrations.deeptutor.learning_tool_adapter import install_learning_tool_factory
        with patch.object(tools, '_new_service', new=lambda: None):
            with self.assertRaises(BackendUnavailable):
                install_learning_tool_factory()


if __name__ == '__main__':
    unittest.main()
