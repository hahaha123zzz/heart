"""教学记忆更正的重试、并发与删除传播，使用隔离SQLite。"""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from database.database import session_scope
from database.models import EvidenceRow, KnowledgeStateRow, LearningEventRow, MemoryChangeRow, Student
from memory_api import router
from tests import test_memory_jobs as fixtures


class TeachingMemoryCorrectionTests(unittest.TestCase):
    setUp = fixtures.MemoryJobTests.setUp
    tearDown = fixtures.MemoryJobTests.tearDown
    count = fixtures.MemoryJobTests.count

    def target(self):
        return self.memory.add_hypothesis('s', self.point, 'set_element_confusion', '混淆元素和集合', .9)

    def test_same_correction_replay_does_not_duplicate_evidence_or_erase_new_summary(self):
        target = self.target()
        first = self.memory.dispute_misconception('s', target.id, '这个判断不符合我的情况')
        counts = [self.count(kind) for kind in (LearningEventRow, EvidenceRow, MemoryChangeRow)]
        with session_scope() as db:
            state = db.scalar(select(KnowledgeStateRow).where(KnowledgeStateRow.student_id == 's'))
            state.last_summary = '更正之后的新讲解'
        repeated = self.memory.dispute_misconception('s', target.id, '这个判断不符合我的情况')
        self.assertEqual(repeated, first)
        self.assertEqual([self.count(kind) for kind in (LearningEventRow, EvidenceRow, MemoryChangeRow)], counts)
        self.assertEqual(self.memory.get_state('s', self.point).last_summary, '更正之后的新讲解')
        self.assertEqual(self.memory.get_state('s', self.point).mastery, .5)

    def test_new_explanation_and_reopened_hypothesis_are_not_old_command_replay(self):
        target = self.target()
        first = self.memory.dispute_misconception('s', target.id, '不符合我的情况')
        second = self.memory.dispute_misconception('s', target.id, '补充说明：元素不是集合')
        self.assertNotEqual(first['event_id'], second['event_id'])
        self.assertEqual(self.memory.dispute_misconception('s', target.id, '补充说明：元素不是集合'), second)
        reopened = next(m for m in self.memory.get_misconceptions('s', self.point) if m.id == target.id)
        reopened.status = 'supported'
        self.memory.repo.save_misconception('s', reopened)
        third = self.memory.dispute_misconception('s', target.id, '补充说明：元素不是集合')
        self.assertNotEqual(third['event_id'], second['event_id'])

    def test_concurrent_repeat_produces_one_correction_event(self):
        target = self.target()
        with ThreadPoolExecutor(max_workers=2) as pool:
            replies = list(pool.map(lambda _: self.memory.dispute_misconception('s', target.id, '这项判断有误'), range(2)))
        self.assertEqual(replies[0], replies[1])
        with session_scope() as db:
            events = db.scalars(select(LearningEventRow).where(LearningEventRow.event_type == 'user_memory_correction')).all()
            self.assertEqual(len(events), 1)

    def test_api_duplicate_and_foreign_student_keep_original_scope(self):
        target = self.target()
        self.memory.ensure_student('other')
        with session_scope() as db:
            db.get(Student, 's').account_type = 'test'
            db.get(Student, 'other').account_type = 'test'
        app = FastAPI(); app.include_router(router)
        fake = SimpleNamespace(orchestrator=SimpleNamespace(memory=self.memory))
        with patch.dict('sys.modules', {'main': fake}), TestClient(app) as client:
            url = '/api/students/s/memory/misconceptions/' + str(target.id) + '/correction'
            first = client.post(url, json={'note': '这项判断有误'})
            self.assertEqual(first.status_code, 200)
            self.assertEqual(client.post(url, json={'note': '这项判断有误'}).json(), first.json())
            foreign = url.replace('/students/s/', '/students/other/')
            self.assertEqual(client.post(foreign, json={'note': '这项判断有误'}).status_code, 404)
            self.assertEqual(client.post(url, json={'note': ' '}).status_code, 422)


if __name__ == '__main__':
    unittest.main()
