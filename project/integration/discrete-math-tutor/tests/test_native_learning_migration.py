"""实际Q5 SQLite + vendor原生事务；不调用模型或正式服务。"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import unittest

from integrations.deeptutor.learning_migration import build_candidate, import_candidate, read_snapshots, EVENT
from integrations.deeptutor.worker import VENDOR_ROOT
from tests import test_q5_learning as fixtures
from unittest.mock import patch

sys.path.insert(0, str(VENDOR_ROOT))
from deeptutor.learning.service import LearningService
from deeptutor.learning.storage import LearningStore, LearningConflictError


class NativeLearningMigrationTests(unittest.TestCase):
    setUp = fixtures.Q5TestBase.setUp
    tearDown = fixtures.Q5TestBase.tearDown
    make_plan = fixtures.Q5TestBase.make_plan
    confirmed_plan = fixtures.Q5TestBase.confirmed_plan

    def candidate(self):
        self.confirmed_plan()
        return read_snapshots(Path(self.temp.name) / 'q5.db', student_id='s', course_id='course-1')[0]

    def store(self):
        return LearningStore(root=Path(self.temp.name) / 'native')

    def test_actual_store_roundtrip_preserves_ids_sources_and_never_mastery(self):
        snapshot = self.candidate()
        row = next(row for row in snapshot['objectives'] if row['objective_id'] == snapshot['path']['current_objective_id'])
        snapshot['progress'] = [item for item in snapshot['progress'] if item['objective_id'] != row['objective_id']]
        snapshot['progress'].append({'path_id': snapshot['path']['path_id'], 'objective_id': row['objective_id'],
            'explained': True, 'understood': True, 'explanation_summary': '已经讲解，学生自报理解',
            'explained_at': '2026-10-26 01:00:00'})
        store = self.store()
        result = import_candidate(snapshot, store)
        progress = LearningService(store).get_or_create(result['native_path_id'])
        self.assertEqual(progress.current_module_id, snapshot['path']['current_module_id'])
        self.assertEqual(progress.modules[0].knowledge_points[0].id, row['objective_id'])
        self.assertIn(row['objective_id'], progress.explained_objectives)
        for field in ('mastery_levels', 'qualitative_mastery', 'quiz_attempts', 'learning_evidence',
                      'learner_mastery_overrides', 'repetition_states', 'review_queue'):
            self.assertFalse(getattr(progress, field), field)
        self.assertIsNone(progress.pending_question)
        topic = store.get_topic(progress.book_id)
        self.assertEqual(topic.metadata.status, 'archived')
        self.assertTrue(all(not source.available for source in topic.sources))
        self.assertEqual(topic.sources[0].metadata['host_q5_source_ref']['version'], 'v1')
        receipt = next(event for event in store.list_events(progress.book_id) if event.event_type == EVENT)
        self.assertEqual(receipt.payload['legacy_snapshot'], snapshot)
        self.assertFalse(result['ready_for_cutover'])

    def test_rerun_is_idempotent_and_does_not_reset_new_native_changes(self):
        snapshot, store = self.candidate(), self.store()
        first = import_candidate(snapshot, store)
        old = store.load(first['native_path_id'])
        old.name = '原生后来改的名称'; store.save(old)
        count = len(store.list_events(old.book_id))
        second = import_candidate(snapshot, LearningStore(root=Path(self.temp.name) / 'native'))
        self.assertEqual(second['status'], 'already_imported')
        self.assertEqual(store.load(old.book_id).name, '原生后来改的名称')
        self.assertEqual(len(store.list_events(old.book_id)), count)

    def test_changed_input_conflicts_instead_of_overwriting(self):
        snapshot, store = self.candidate(), self.store()
        first = import_candidate(snapshot, store)
        snapshot['path']['revision'] += 1
        with self.assertRaisesRegex(ValueError, '禁止覆盖'):
            import_candidate(snapshot, store)
        self.assertEqual(store.load(first['native_path_id']).version, 1)

    def test_owner_course_namespace_and_readonly_input(self):
        snapshot = self.candidate()
        path = Path(self.temp.name) / 'q5.db'
        before = path.read_bytes()
        self.assertEqual(read_snapshots(path, student_id='other', course_id='course-1'), [])
        self.assertEqual(read_snapshots(path, student_id='s', course_id='other'), [])
        first, _ = build_candidate(snapshot)
        other = deepcopy(snapshot); other['path']['student_id'] = 'other'; other['bindings'] = []
        second, _ = build_candidate(other)
        self.assertNotEqual(first.book_id, second.book_id)
        self.assertEqual(path.read_bytes(), before)

    def test_unsupported_navigation_draft_and_missing_cursor_fail_closed(self):
        snapshot = self.candidate()
        for change in ({'kind': 'textbook_navigation'}, {'plan_confirmed': False},
                       {'current_objective_id': 'missing'}):
            candidate = deepcopy(snapshot); candidate['path'].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                build_candidate(candidate)

    def test_unknown_cyclic_and_duplicate_relations_use_native_validation(self):
        snapshot = self.candidate()
        point = snapshot['objectives'][0]
        for refs in (['missing'], [point['objective_id']]):
            candidate = deepcopy(snapshot); candidate['objectives'][0]['prerequisite_ids'] = refs
            with self.assertRaises(ValueError):
                build_candidate(candidate)
        candidate = deepcopy(snapshot)
        candidate['objectives'].append(deepcopy(candidate['objectives'][0]))
        with self.assertRaises(ValueError):
            build_candidate(candidate)
        candidate = deepcopy(snapshot)
        first, second = candidate['objectives'][:2]
        first['prerequisite_ids'] = [second['objective_id']]
        second['prerequisite_ids'] = [first['objective_id']]
        with self.assertRaises(ValueError):
            build_candidate(candidate)

    def test_current_objective_is_preserved_when_not_first_in_module(self):
        snapshot = self.candidate()
        module = snapshot['modules'][0]
        objectives = sorted((row for row in snapshot['objectives'] if row['module_id'] == module['module_id']),
                            key=lambda row: row['position'])
        snapshot['path']['current_objective_id'] = objectives[1]['objective_id']
        progress, _ = build_candidate(snapshot)
        self.assertEqual(progress.current_kp_index, 1)
        self.assertEqual(progress.modules[0].knowledge_points[progress.current_kp_index].id, objectives[1]['objective_id'])

    def test_native_transaction_rolls_back_state_topic_and_receipt_together(self):
        from deeptutor.learning.storage import LearningTransaction
        snapshot, store = self.candidate(), self.store()
        original = LearningTransaction.emit
        def fail(tx, event, *args, **kwargs):
            if event == EVENT:
                raise RuntimeError('migration receipt failure')
            return original(tx, event, *args, **kwargs)
        with patch.object(LearningTransaction, 'emit', fail), self.assertRaises(RuntimeError):
            import_candidate(snapshot, store)
        self.assertEqual(store.list_all(), [])

    def test_cli_rejects_output_outside_isolated_candidate_root(self):
        self.candidate()
        output = Path(self.temp.name) / 'not-an-allowed-root'
        script = Path(__file__).resolve().parents[1] / 'scripts/check_native_learning_migration.py'
        result = subprocess.run([sys.executable, str(script), '--source-snapshot',
            str(Path(self.temp.name) / 'q5.db'), '--student', 's', '--course', 'course-1',
            '--output', str(output)], capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(output.exists())

    def test_invalid_candidate_leaves_no_native_path(self):
        snapshot, store = self.candidate(), self.store()
        snapshot['objectives'][0]['source_refs'] = []
        with self.assertRaises(ValueError):
            import_candidate(snapshot, store)
        self.assertEqual(store.list_all(), [])

    def test_concurrent_import_has_one_receipt_and_native_cas_still_works(self):
        snapshot, store = self.candidate(), self.store()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: import_candidate(snapshot, store), range(2)))
        self.assertEqual(sorted(item['status'] for item in results), ['already_imported', 'imported'])
        path_id = results[0]['native_path_id']
        self.assertEqual(sum(event.event_type == EVENT for event in store.list_events(path_id)), 1)
        first, stale = store.load(path_id), store.load(path_id)
        first.name = '新版本'; store.save(first)
        with self.assertRaises(LearningConflictError):
            store.save(stale)


if __name__ == '__main__':
    unittest.main()
