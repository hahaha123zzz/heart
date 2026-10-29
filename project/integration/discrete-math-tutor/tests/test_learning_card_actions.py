"""展示卡片持久动作；隔离SQLite，不创建学习成绩。"""
import concurrent.futures
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch
from database.repository import Repository
from database.database import session_scope
from database.models import MemoryControlRow
from database.models import PDFCitationRow
from copy import deepcopy
from learning_cards_api import router
from tests import test_q5_learning as fixtures


class CardActionTests(fixtures.Q5TestBase):
    def setUp(self):
        super().setUp()
        self.card = {'schema': 'learning-cards/v1', 'card_id': 'step1', 'kind': 'step_reveal',
            'revision': 2, 'view_revision': 0, 'title': '变量', 'memory_epoch': 0,
            'allowed_actions': ['set_expanded'], 'source_refs': [{'document_id': 'doc', 'version': 'v1'}],
            'steps': [{'title': '操纵', 'body': '改变条件'}, {'title': '测量', 'body': '观察反应'}]}
        self.conversation = Repository().append_conversation('s', 'assistant', '已保存的讲解', session_id='sess',
            selection_ref={'section_title': '变量', 'learning_cards': [self.card]})
        self.key = {'student_id': 's', 'session_id': 'sess', 'conversation_id': self.conversation}
        app = FastAPI(); app.include_router(router)
        self.client = TestClient(app)
        self.sources = patch('knowledge.pdf_reader.document', return_value={'version': 'v1'})
        self.document = self.sources.start()

    def tearDown(self):
        self.client.close(); self.sources.stop(); super().tearDown()

    def payload(self, **changes):
        return self.key | {'card_id': 'step1', 'command_id': 'cmd1', 'base_revision': 0, 'expanded': [0, 1]} | changes

    def test_persist_restore_and_same_command_replay(self):
        result = self.client.post('/api/learning/cards/expand', json=self.payload())
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['learning_cards'][0]['view_revision'], 1)
        self.assertEqual(result.json(), self.client.post('/api/learning/cards/expand', json=self.payload()).json())
        self.assertEqual(result.json(), self.client.post('/api/learning/cards/view', json=self.key).json())
        self.assertEqual(Repository().get_conversation_with_figures('s')[0]['content'], '已保存的讲解')
        self.assertEqual(self.client.post('/api/learning/cards/expand', json=self.payload(expanded=[0])).status_code, 409)

    def test_scope_source_epoch_and_unregistered_action(self):
        for override in ({'student_id': 'other'}, {'session_id': 'other'}, {'card_id': 'fake'}):
            self.assertEqual(self.client.post('/api/learning/cards/expand', json=self.payload(**override)).status_code, 404)
        self.assertEqual(self.client.post('/api/learning/cards/expand', json=self.payload(expanded=[6])).status_code, 422)
        self.assertEqual(self.client.post('/api/learning/cards/expand', json=self.payload(script='alert(1)')).status_code, 422)
        self.document.return_value = {'version': 'v2'}
        self.assertEqual(self.client.post('/api/learning/cards/view', json=self.key).status_code, 410)
        self.document.return_value = {'version': 'v1'}
        with session_scope() as db:
            db.add(MemoryControlRow(student_id='s', knowledge_point='变量', epoch=1))
        self.assertEqual(self.client.post('/api/learning/cards/expand', json=self.payload()).status_code, 410)

    def test_parallel_expansion_has_one_winner(self):
        def apply(n):
            return self.client.post('/api/learning/cards/expand', json=self.payload(command_id=f'c{n}')).status_code
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(apply, (1, 2))), [200, 409])

    def test_native_proxy_uses_only_server_binding_and_updates_projection(self):
        from knowledge.course_config import COURSE_ID
        binding = {'student_id': 's', 'session_id': 'sess', 'course_id': COURSE_ID, 'request_id': 'native-r1',
            'task_id': 'native-task', 'task_revision': 1, 'path_id': 'p', 'question_id': 'q', 'memory_epoch': 0}
        with session_scope() as db:
            row = db.get(PDFCitationRow, self.conversation)
            ref = deepcopy(row.reference)
            ref['_native_assessment'] = binding
            ref['learning_cards'][0]['schema'] = 'learning-cards/v2'
            row.reference = ref
        payload = self.payload() | {'action': 'set_expanded'}
        self.assertEqual(self.client.post('/api/learning/cards/action', json=payload).status_code, 503)
        result = {'learning_cards': [dict(self.card, schema='learning-cards/v2', revision=3)], 'revision': 3}
        with patch.dict('os.environ', DEEPTUTOR_NATIVE_ENABLED='1'), patch('integrations.deeptutor.client.DeepTutorBackend._post', return_value=result) as backend:
            response = self.client.post('/api/learning/cards/action', json=payload)
            self.assertEqual(response.status_code, 200, response.text)
            sent = backend.call_args.args[1]
            self.assertEqual(sent['task_id'], 'native-task')
            self.assertEqual(sent['question_id'], 'q')
            self.assertNotIn('conversation_id', sent)
            self.assertEqual(self.client.post('/api/learning/cards/action', json=payload | {'question_id': 'evil'}).status_code, 422)
        history = Repository().get_conversation_with_figures('s')[0]['selection_ref']
        self.assertNotIn('_native_assessment', history)
        self.assertEqual(history['learning_cards'][0]['revision'], 3)
