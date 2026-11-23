"""真实 SQLite/ContextBuilder 回归：题卡完成状态进入后续模型历史。"""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from deeptutor.services.session.sqlite_store import SQLiteSessionStore
from deeptutor.services.session.context_builder import ContextBuilder
from deeptutor.services.llm.config import LLMConfig
from integrations.deeptutor.native_history import install_question_history
from tests.test_native_delivery import quiz


class QuestionHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = SQLiteSessionStore(Path(self.temp.name)/'history.db')
        install_question_history()
        await self.store.create_session(session_id='s')
        user = await self.store.add_message('s','user','出一道变量选择题')
        turn = await self.store.begin_turn('s','deep_question')
        self.turn_id = turn['id']
        self.message_id = await self.store.add_message('s','assistant','现在为你出题。',
            capability='deep_question',parent_message_id=user)
        await self.store.link_turn_message(self.turn_id,self.message_id)
        await self.store.append_turn_event(self.turn_id,{'type':'result','metadata':quiz()})
        await self.store.update_turn_status(self.turn_id,'completed')
        self.scope = patch('integrations.deeptutor.learning_tool_adapter.current_learning_context',
            return_value=SimpleNamespace(session_id='s'))
        self.scope.start()

    async def asyncTearDown(self):
        self.scope.stop()
        self.temp.cleanup()

    async def test_complete_card_reaches_native_model_history_without_private_answer(self):
        config=LLMConfig(model='test-model',api_key='test-key',binding='openai')
        built=await ContextBuilder(self.store).build(session_id='s',llm_config=config,language='zh')
        assistant=next(row['content'] for row in built.model_history if row['role']=='assistant')
        self.assertIn('已生成 1 道练习题',assistant)
        self.assertIn('哪个变量由研究者操纵',assistant)
        for private in ('correct_answer','explanation','私有解析','现在为你出题'):
            self.assertNotIn(private,assistant)
        raw=await self.store.get_messages('s')
        self.assertEqual(raw[-1]['content'],'现在为你出题。')

    async def test_other_session_and_unscoped_reads_are_unchanged(self):
        with patch('integrations.deeptutor.learning_tool_adapter.current_learning_context',return_value=None):
            self.assertEqual((await self.store.get_messages_for_context('s'))[-1]['content'],'现在为你出题。')
        with patch('integrations.deeptutor.learning_tool_adapter.current_learning_context',return_value=SimpleNamespace(session_id='other')):
            self.assertEqual((await self.store.get_messages_for_context('s'))[-1]['content'],'现在为你出题。')

    async def test_edit_branch_does_not_import_sibling_question(self):
        branch=await self.store.add_message('s','user','新分支',parent_message_id=None)
        rows=await self.store.get_messages_for_context('s',leaf_message_id=branch)
        self.assertEqual([row['content'] for row in rows],['新分支'])

    async def test_failed_or_incomplete_questions_are_not_marked_delivered(self):
        await self.store.append_turn_event(self.turn_id,{'type':'result','metadata':quiz(False)})
        self.assertEqual((await self.store.get_messages_for_context('s'))[-1]['content'],'现在为你出题。')
        turn=await self.store.begin_turn('s','deep_question')
        message=await self.store.add_message('s','assistant','出题失败。',capability='deep_question')
        await self.store.link_turn_message(turn['id'],message)
        await self.store.append_turn_event(turn['id'],{'type':'result','metadata':quiz()})
        self.assertTrue(await self.store.update_turn_status(turn['id'],'failed'))
        self.assertEqual((await self.store.get_messages_for_context('s'))[-1]['content'],'出题失败。')


class NavigationTeachingScopeTests(unittest.TestCase):
    def test_navigation_does_not_receive_explanation_plan(self):
        from integrations.deeptutor.teaching_prompt_adapter import teaching_snapshot
        identity=SimpleNamespace(student_id='s',session_id='s',request_id='r',task_id='t',task_revision=1)
        with patch.dict('os.environ',{'ADAPTIVE_TUTORING_ENABLED':'1'}):
            navigation=teaching_snapshot('请翻到PDF第2页，只需翻页，不需要解释教材。',identity=identity)
            self.assertNotIn('strategy_plan',navigation)
            explanation=teaching_snapshot('不要跳转页面，解释自变量。',identity=identity)
            self.assertIn('strategy_plan',explanation)
