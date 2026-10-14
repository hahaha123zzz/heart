"""历史标识使用隔离 SQLite；不读取实际学生数据库。"""
import unittest
import sys
from types import SimpleNamespace
from unittest.mock import patch
from tests import test_memory_jobs as fixtures


class ConversationIdentityTests(unittest.TestCase):
    setUp = fixtures.MemoryJobTests.setUp
    tearDown = fixtures.MemoryJobTests.tearDown

    def test_stable_distinct_ids_and_student_filter(self):
        repo = self.memory.repo
        self.memory.ensure_student('other')
        first = repo.append_conversation('s', 'assistant', '相同内容')
        second = repo.append_conversation('s', 'assistant', '相同内容')
        repo.append_conversation('other', 'assistant', '其他学生')
        rows = repo.get_conversation_with_figures('s')
        self.assertEqual([row['id'] for row in rows], [first, second])
        self.assertNotEqual(first, second)
        self.assertEqual(repo.get_conversation_with_figures('s'), rows)
        self.assertEqual([row['id'] for row in repo.get_conversation_with_figures('s', 1)], [second])

    def test_http_history_preserves_id_and_selection_references(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from web_api import router

        ref = {'textbook_sources': ['集合定义'], 'pdf_references': [{'source_index': 0}]}
        identifier = self.memory.repo.append_conversation('s', 'assistant', '说明 [1]', selection_ref=ref)
        app = FastAPI()
        app.include_router(router)
        # 替换路由的延迟 main 导入，避免初始化真实 orchestrator。
        with patch.dict(sys.modules, {'main': SimpleNamespace(orchestrator=SimpleNamespace(memory=self.memory))}):
            response = TestClient(app).get('/api/students/s/conversation')
        self.assertEqual(response.status_code, 200)
        row = response.json()[0]
        self.assertEqual(row['id'], identifier)
        self.assertEqual(row['selection_ref'], ref)
        self.assertEqual(row['textbook_sources'], ref['textbook_sources'])
        self.assertEqual(row['pdf_references'], ref['pdf_references'])


if __name__ == '__main__':
    unittest.main()
