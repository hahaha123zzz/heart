"""真实原生应用/SQLite与上游提示组装器；模型能力受控，不冒充真实模型验收。"""
import json
import os
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from integrations.deeptutor.native_bridge import NativeTurnBridge, digest
from integrations.deeptutor.native_contract import NativeTurnReply
from tests import test_deeptutor_native_runtime as fixtures

request, key = fixtures.request, fixtures.key


class NativeWorkerMountTests(unittest.TestCase):
    def test_real_worker_registers_native_routes_only_when_explicitly_enabled(self):
        from integrations.deeptutor import worker
        for enabled in ('0', '1'):
            with self.subTest(enabled=enabled), tempfile.TemporaryDirectory() as directory:
                app = FastAPI()
                with (patch.dict(os.environ, {'DEEPTUTOR_NATIVE_ENABLED': enabled}),
                      patch.dict(sys.modules, {'deeptutor.api.main': SimpleNamespace(app=app)}),
                      patch.object(sys, 'argv', ['worker', '--home', directory]),
                      patch.object(worker, 'prepare'), patch('uvicorn.run') as serve):
                    worker.main()
                self.assertTrue(serve.called)
                paths = set(app.openapi()['paths'])
                self.assertEqual('/internal/heart/native/start' in paths, enabled == '1')


class NativeTeachingPromptTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = fixtures.NativeRuntimeTests.__dict__['setUpClass']
    asyncSetUp = fixtures.NativeRuntimeTests.asyncSetUp
    asyncTearDown = fixtures.NativeRuntimeTests.asyncTearDown
    finished = fixtures.NativeRuntimeTests.finished
    _collect = fixtures.NativeRuntimeTests._collect
    wait_status = fixtures.NativeRuntimeTests.wait_status

    async def test_preferences_reach_native_prompt_and_do_not_leak_to_next_turn(self):
        req = request(content='直接解释自变量，这次少提问、多举例',
                      teaching_preferences={'question_frequency': 1., 'example_density': 0.})
        await self.bridge.start(req)
        await self.finished(req)
        prompt = self.calls[0]['prompt']
        self.assertEqual(prompt.count('## host_teaching_style'), 1)
        self.assertIn('本轮直接讲解', prompt)
        self.assertIn('不主动追加检查题', prompt)
        self.assertIn('多用相关辅助例子', prompt)
        self.assertIn('推断的联系注明是教学分析', prompt)
        self.assertEqual(len(self.calls), 1)
        again = await NativeTurnBridge(self.sessions).start(req)
        self.assertTrue(again['turn_id'])
        self.assertEqual(len(self.calls), 1)
        next_req = request(request_id='next', task_id='next', content='继续')
        await self.bridge.start(next_req)
        await self.finished(next_req)
        self.assertNotIn('本轮直接讲解', self.calls[1]['prompt'])
        self.assertNotIn('多用相关辅助例子', self.calls[1]['prompt'])
        with self.bridge.scope(self.bridge.entry(req)) as app:
            prefs = (await app.container.store_provider.get().get_session(self.bridge.entry(req)['native_session_id']))['preferences']
            from deeptutor.capabilities.mastery.pipeline import MasteryPromptAssembler
            from deeptutor.core.context import UnifiedContext
            context = UnifiedContext(session_id=self.bridge.entry(req)['native_session_id'],
                                     user_message=req.content, metadata={'mastery_session_mode': 'review'})
            prompt = MasteryPromptAssembler(prompts={'session': {'review': '原生路径复习模式'}}, language='zh').system_prompt(
                context=context, tool_manifest='')
            self.assertIn('## mastery_session_mode', prompt)
            self.assertIn('本轮直接讲解', prompt)
            self.assertEqual(prompt.count('## host_teaching_style'), 1)
            self.assertEqual(context.metadata['mastery_session_mode'], 'review')
        self.assertNotIn('example_density', prefs)

    async def test_wait_resume_keeps_style_while_another_session_uses_guidance(self):
        req = request(capability='ask_questions', content='直接解释，但先确认对象',
                      teaching_preferences={'question_frequency': 0.})
        await self.bridge.start(req)
        await self.wait_status(req, 'waiting_input')
        other = request(session_id='other', request_id='other', task_id='other', content='带我思考')
        await self.bridge.start(other)
        await self.finished(other)
        self.assertIn('本轮引导探索', self.calls[1]['prompt'])
        self.assertNotIn('本轮直接讲解', self.calls[1]['prompt'])
        await self.bridge.command(key(req, NativeTurnReply, command_id='answer', text='自变量'))
        await self.finished(req)
        resumed = next(call['resumed_prompt'] for call in self.calls if 'resumed_prompt' in call)
        self.assertIn('本轮直接讲解', resumed)
        self.assertNotIn('本轮引导探索', resumed)

    async def test_changed_preference_conflicts_with_durable_receipt(self):
        req = request(teaching_preferences={'question_frequency': 0.})
        await self.bridge.start(req)
        await self.finished(req)
        with self.assertRaises(HTTPException) as error:
            await self.bridge.start(req.model_copy(update={'teaching_preferences': req.teaching_preferences.model_copy(
                update={'question_frequency': 1.})}))
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(len(self.calls), 1)

    async def test_old_schema_and_receipt_are_compatible(self):
        with self.sessions._connect() as db:
            db.execute('ALTER TABLE native_requests DROP COLUMN teaching_style')
        self.bridge = NativeTurnBridge(self.sessions)
        req = request()
        await self.bridge.start(req)
        await self.finished(req)
        entry = self.bridge.entry(req)
        payload = req.receipt_payload()
        # 旧客户端的收据只含这些字段；新增字段的默认值不得改变哈希。
        self.assertEqual(set(payload), {'student_id','course_id','session_id','request_id','task_id',
            'task_revision','memory_epoch','material_versions','course_title','content','capability'})
        self.assertEqual(entry['digest'], digest(payload))
        self.assertEqual(json.loads(entry['teaching_style'])['mode'], 'auto')

    async def test_other_session_cannot_assemble_with_current_style(self):
        from deeptutor.agents.loop.prompt_blocks import LoopPromptAssembler
        from deeptutor.core.context import UnifiedContext
        from integrations.deeptutor.client import BackendUnavailable
        req = request()
        await self.bridge.start(req)
        await self.finished(req)
        with self.bridge.scope(self.bridge.entry(req)):
            with self.assertRaises(BackendUnavailable):
                LoopPromptAssembler(prompts={}, language='zh').system_prompt(
                    context=UnifiedContext(session_id='another', user_message='你好'), tool_manifest='')


if __name__ == '__main__':
    unittest.main()
