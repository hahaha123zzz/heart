"""真实原生账户/工作区/会话/学习库；不执行模型或在线Q5写入。"""
import sys
import unittest
from unittest.mock import patch

from integrations.deeptutor.worker import VENDOR_ROOT
sys.path.insert(0, str(VENDOR_ROOT))

from integrations.deeptutor.session_bridge import SessionBindingRequest
from integrations.deeptutor.native_bridge import NativeTurnBridge
from tests import test_deeptutor_native_runtime as fixtures


def binding(**changes):
    return SessionBindingRequest(**(dict(student_id='student-a', course_id='psychology',
        course_title='实验心理学', session_id='tab-a') | changes))


def snapshot():
    return {'path': {'path_id': 'q5-original', 'student_id': 'student-a', 'course_id': 'psychology',
        'kind': 'mastery_goal', 'name': '变量学习', 'goal': '区分实验变量', 'plan_confirmed': True,
        'status': 'active', 'revision': 7, 'current_module_id': 'module', 'current_objective_id': 'point'},
        'modules': [{'path_id': 'q5-original', 'module_id': 'module', 'name': '实验变量',
                     'position': 0, 'objective': '区分操纵和测量', 'pass_threshold': .7}],
        'objectives': [{'path_id': 'q5-original', 'module_id': 'module', 'objective_id': 'point',
            'position': 0, 'name': '自变量', 'knowledge_type': 'concept', 'prerequisite_ids': [],
            'required_visual_tasks': [], 'source_refs': [{'document_id': 'doc', 'version': 'v1'}]}],
        'progress': [], 'bindings': [{'student_id': 'student-a', 'session_id': 'tab-a',
            'active_path_id': 'q5-original', 'mode': 'study', 'teaching_strategy': 'teach_first'}]}


class NativeLearningBindingTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.NativeRuntimeTests.asyncSetUp
    asyncTearDown = fixtures.NativeRuntimeTests.asyncTearDown

    async def test_scope_creation_is_idempotent_ordinary_user_and_model_free(self):
        from deeptutor.multi_user.identity import get_user_by_id
        with patch('integrations.deeptutor.native_bridge.model_config', side_effect=AssertionError('不读取模型配置')):
            first = await self.bridge.bind_scope(binding())
            second = await NativeTurnBridge(self.sessions).bind_scope(binding())
        self.assertEqual(first, second)
        self.assertEqual(get_user_by_id(first['user_id'])[1]['role'], 'user')
        self.assertEqual(self.calls, [])
        with self.sessions._connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM native_requests').fetchone()[0], 0)
        text = ''.join(path.read_text(encoding='utf-8') for path in self.home.rglob('*.json'))
        self.assertNotIn('fixture-key', text)

    async def test_scope_isolates_student_course_and_session(self):
        first = await self.bridge.bind_scope(binding())
        other_tab = await self.bridge.bind_scope(binding(session_id='tab-b'))
        other_course = await self.bridge.bind_scope(binding(course_id='math'))
        other_user = await self.bridge.bind_scope(binding(student_id='student-b'))
        self.assertEqual(first['user_id'], other_tab['user_id'])
        self.assertEqual(first['workspace_id'], other_tab['workspace_id'])
        self.assertNotEqual(first['native_session_id'], other_tab['native_session_id'])
        self.assertNotEqual(first['workspace_id'], other_course['workspace_id'])
        self.assertNotEqual(first['user_id'], other_user['user_id'])

    async def test_candidate_uses_real_workspace_store_and_restores_session_path(self):
        from integrations.deeptutor.learning_migration import bind_candidate_sessions
        from deeptutor.learning.storage import LearningStore
        from deeptutor.services.session import get_session_store
        from deeptutor.services.workspace.context import workspace_context
        from deeptutor.services.workspace import get_content_workspace_service
        original = snapshot()
        first = await bind_candidate_sessions(original, self.bridge)
        repeated = await bind_candidate_sessions(original, NativeTurnBridge(self.sessions))
        self.assertEqual(first['migration']['status'], 'imported')
        self.assertEqual(repeated['migration']['status'], 'already_imported')
        mapped = first['bindings'][0]
        with self.bridge.user_scope(mapped['user_id']), workspace_context(mapped['workspace_id']):
            store = LearningStore()
            path_id = first['migration']['native_path_id']
            self.assertEqual(store.path_id_for_session(mapped['native_session_id']), path_id)
            self.assertEqual(store.list_session_ids(path_id), [mapped['native_session_id']])
            self.assertTrue(store.db_path.is_relative_to(self.home))
            self.assertTrue(store.db_path.resolve().is_relative_to(
                get_content_workspace_service().binding_by_id(mapped['workspace_id']).root.resolve()))
            self.assertNotEqual(store.db_path.parent, self.home / 'learning')
            self.assertIsNotNone(await get_session_store().get_session(mapped['native_session_id']))
            self.assertEqual(store.get_topic(path_id).metadata.status, 'archived')
            self.assertEqual(store.count_learning_evidence(path_id), 0)
        self.assertEqual(snapshot(), original)
        self.assertFalse(first['ready_for_cutover'])
        self.assertEqual(self.calls, [])

    async def test_existing_other_path_is_not_silently_replaced(self):
        from integrations.deeptutor.learning_migration import bind_candidate_sessions
        from deeptutor.learning.models import LearningProgress
        from deeptutor.learning.storage import LearningStore
        from deeptutor.services.workspace.context import workspace_context
        mapped = await self.bridge.bind_scope(binding())
        with self.bridge.user_scope(mapped['user_id']), workspace_context(mapped['workspace_id']):
            store = LearningStore(); store.save(LearningProgress(book_id='existing-native-path'))
            store.bind_session('existing-native-path', mapped['native_session_id'])
        with self.assertRaisesRegex(ValueError, '会话已绑定其他路径'):
            await bind_candidate_sessions(snapshot(), self.bridge)
        with self.bridge.user_scope(mapped['user_id']), workspace_context(mapped['workspace_id']):
            store = LearningStore()
            self.assertEqual(store.path_id_for_session(mapped['native_session_id']), 'existing-native-path')
            self.assertEqual(store.list_all(), ['existing-native-path'])

    async def test_missing_or_foreign_bindings_fail_before_account_creation(self):
        from integrations.deeptutor.learning_migration import bind_candidate_sessions
        for values in ([], [dict(snapshot()['bindings'][0], student_id='other')]):
            original = snapshot(); original['bindings'] = values
            with self.subTest(values=values), self.assertRaises(ValueError):
                await bind_candidate_sessions(original, self.bridge)
        with self.sessions._connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM native_courses').fetchone()[0], 0)

    async def test_native_lease_rejects_second_session_until_original_releases(self):
        from integrations.deeptutor.learning_migration import bind_candidate_sessions
        from deeptutor.learning.storage import LearningStore, PathLeaseConflictError
        from deeptutor.services.workspace.context import workspace_context
        original = snapshot()
        original['bindings'].append(dict(original['bindings'][0], session_id='tab-b'))
        result = await bind_candidate_sessions(original, self.bridge)
        first, second = result['bindings']
        with self.bridge.user_scope(first['user_id']), workspace_context(first['workspace_id']):
            store = LearningStore(); path_id = result['migration']['native_path_id']
            store.acquire_path_lease(path_id, first['native_session_id'], 'turn-a', bind_session=False)
            with self.assertRaises(PathLeaseConflictError):
                store.acquire_path_lease(path_id, second['native_session_id'], 'turn-b', bind_session=False)
            self.assertTrue(store.release_path_lease(path_id, turn_id='turn-a'))
            store.acquire_path_lease(path_id, second['native_session_id'], 'turn-b', bind_session=False)
            self.assertTrue(store.release_path_lease(path_id, turn_id='turn-b'))

    async def test_two_paths_share_workspace_without_sharing_session_binding(self):
        from integrations.deeptutor.learning_migration import bind_candidate_sessions
        from deeptutor.learning.storage import LearningStore
        from deeptutor.services.workspace.context import workspace_context
        first = await bind_candidate_sessions(snapshot(), self.bridge)
        other = snapshot(); other['path']['path_id'] = 'second-q5-path'
        other['bindings'][0].update(active_path_id='second-q5-path', session_id='tab-b')
        for row in other['modules'] + other['objectives']:
            row['path_id'] = 'second-q5-path'
        second = await bind_candidate_sessions(other, self.bridge)
        left, right = first['bindings'][0], second['bindings'][0]
        self.assertEqual(left['workspace_id'], right['workspace_id'])
        with self.bridge.user_scope(left['user_id']), workspace_context(left['workspace_id']):
            store = LearningStore()
            self.assertEqual(store.path_id_for_session(left['native_session_id']), first['migration']['native_path_id'])
            self.assertEqual(store.path_id_for_session(right['native_session_id']), second['migration']['native_path_id'])
            self.assertEqual(len(store.list_all()), 2)


if __name__ == '__main__':
    unittest.main()
