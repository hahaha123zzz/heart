"""真实原生会话偏好恢复；旧理解/活动不升级为评分或自动执行。"""
import unittest
from unittest.mock import AsyncMock, patch

from tests import test_native_learning_binding as fixtures
from integrations.deeptutor.learning_migration import bind_candidate_sessions


class NativeLearningSessionStateTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.NativeLearningBindingTests.asyncSetUp
    asyncTearDown = fixtures.NativeLearningBindingTests.asyncTearDown

    async def preferences(self, mapped):
        from deeptutor.services.session import get_session_store
        from deeptutor.services.workspace.context import workspace_context
        with self.bridge.user_scope(mapped['user_id']), workspace_context(mapped['workspace_id']):
            return (await get_session_store().get_session(mapped['native_session_id']))['preferences']

    async def test_mode_and_understood_restore_without_mastery_or_turns(self):
        from deeptutor.learning.storage import LearningStore
        from deeptutor.services.workspace.context import workspace_context
        snapshot = fixtures.snapshot()
        snapshot['progress'] = [{'path_id': 'q5-original', 'objective_id': 'point',
            'explained': False, 'understood': True, 'understood_at': '2026-10-27 01:00:00'}]
        result = await bind_candidate_sessions(snapshot, self.bridge)
        mapped = result['bindings'][0]
        preferences = await self.preferences(mapped)
        self.assertEqual(preferences['mastery_session_mode'], 'study')
        self.assertEqual(preferences['mastery_path_id'], result['migration']['native_path_id'])
        receipt = preferences['heart_q5_session_migration']
        self.assertEqual(receipt['self_reported_understood'][0]['objective_id'], 'point')
        self.assertFalse(receipt['assessed_mastery'])
        with self.bridge.user_scope(mapped['user_id']), workspace_context(mapped['workspace_id']):
            store = LearningStore()
            progress = store.load(preferences['mastery_path_id'])
            self.assertFalse(progress.learner_mastery_overrides)
            self.assertFalse(progress.mastery_levels)
            self.assertFalse(progress.explained_objectives)
            self.assertEqual(store.count_learning_evidence(progress.book_id), 0)
            self.assertEqual(store.get_topic(progress.book_id).metadata.status, 'archived')
        self.assertEqual(self.calls, [])

    async def test_rerun_preserves_later_native_mode_and_other_preferences(self):
        from deeptutor.services.session import get_session_store
        from deeptutor.services.workspace.context import workspace_context
        snapshot = fixtures.snapshot()
        result = await bind_candidate_sessions(snapshot, self.bridge)
        mapped = result['bindings'][0]
        with self.bridge.user_scope(mapped['user_id']), workspace_context(mapped['workspace_id']):
            await get_session_store().update_session_preferences(mapped['native_session_id'],
                {'mastery_session_mode': 'review', 'custom_display': 'preserved'})
        again = await bind_candidate_sessions(snapshot, self.bridge)
        preferences = await self.preferences(mapped)
        self.assertEqual(preferences['mastery_session_mode'], 'review')
        self.assertEqual(preferences['custom_display'], 'preserved')
        self.assertEqual(again['migration']['session_state_statuses'], ['already_restored'])

    async def test_existing_explicit_native_mode_is_not_overwritten(self):
        from deeptutor.services.session import get_session_store
        from deeptutor.services.workspace.context import workspace_context
        mapped = await self.bridge.bind_scope(fixtures.binding())
        with self.bridge.user_scope(mapped['user_id']), workspace_context(mapped['workspace_id']):
            await get_session_store().update_session_preferences(mapped['native_session_id'], {'mastery_session_mode': 'outline'})
        with self.assertRaisesRegex(ValueError, '禁止覆盖'):
            await bind_candidate_sessions(fixtures.snapshot(), self.bridge)
        self.assertEqual((await self.preferences(mapped))['mastery_session_mode'], 'outline')

    async def test_invalid_mode_or_foreign_plan_rejected_before_scope_creation(self):
        for mode, plan in (('invalid', None), ('study', {'bad': 'plan'})):
            snapshot = fixtures.snapshot()
            snapshot['bindings'][0].update(mode=mode, session_plan=plan)
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                await bind_candidate_sessions(snapshot, self.bridge)
        with self.sessions._connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM native_courses').fetchone()[0], 0)

    async def test_two_sessions_keep_different_modes(self):
        snapshot = fixtures.snapshot()
        snapshot['bindings'].append(dict(snapshot['bindings'][0], session_id='tab-b', mode='review'))
        result = await bind_candidate_sessions(snapshot, self.bridge)
        modes = [(await self.preferences(mapped))['mastery_session_mode'] for mapped in result['bindings']]
        self.assertEqual(modes, ['study', 'review'])

    async def test_session_plan_is_validated_and_preserved_but_not_activated(self):
        snapshot = fixtures.snapshot()
        plan = {'plan_id': 'plan1', 'revision': 2, 'student_id': 'student-a', 'session_id': 'tab-a',
            'course_id': 'psychology', 'path_id': 'q5-original', 'path_revision': 6,
            'status': 'active', 'current_item_id': 'item1', 'request': {'goal': '区分变量'},
            'items': [{'item_id': 'item1', 'objective_id': 'point', 'kind': 'explain', 'title': '自变量',
                'source_refs': [{'document_id': 'doc', 'version': 'v1'}], 'estimated_minutes': 10,
                'order_reason': '先辨认操纵对象', 'completion_criterion': '讲解完成'}]}
        snapshot['bindings'][0]['session_plan'] = plan
        result = await bind_candidate_sessions(snapshot, self.bridge)
        receipt = (await self.preferences(result['bindings'][0]))['heart_q5_session_migration']
        self.assertEqual(receipt['legacy_session_plan']['current_item_id'], 'item1')
        self.assertNotIn('items', receipt['legacy_session_plan'])
        self.assertNotIn('request', receipt['legacy_session_plan'])
        self.assertTrue(receipt['session_plan_requires_revalidation'])
        self.assertFalse(receipt['activated'])
        for key, value in (('student_id', 'other'), ('session_id', 'other'),
                           ('course_id', 'other'), ('path_id', 'other')):
            plan[key], old = value, plan[key]
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, '不属于'):
                await bind_candidate_sessions(snapshot, self.bridge)
            plan[key] = old

    async def test_failed_preference_write_does_not_claim_restoration_and_retry_recovers(self):
        from deeptutor.services.session import get_session_store
        from deeptutor.services.workspace.context import workspace_context
        mapped = await self.bridge.bind_scope(fixtures.binding())
        with self.bridge.user_scope(mapped['user_id']), workspace_context(mapped['workspace_id']):
            store = get_session_store()
            with patch.object(store, 'update_session_preferences', new=AsyncMock(return_value=False)):
                with self.assertRaisesRegex(ValueError, '状态恢复失败'):
                    await bind_candidate_sessions(fixtures.snapshot(), self.bridge)
        self.assertNotIn('heart_q5_session_migration', await self.preferences(mapped))
        result = await bind_candidate_sessions(fixtures.snapshot(), self.bridge)
        self.assertEqual(result['migration']['session_state_statuses'], ['restored'])


if __name__ == '__main__':
    unittest.main()
