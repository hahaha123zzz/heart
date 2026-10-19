"""实际运行上游 AgentLoop；仅替换模型传输，不模拟循环或工具调度。"""
import asyncio
from copy import deepcopy
import hashlib
import importlib.util
import os
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from integrations.deeptutor.agentic_bridge import AgenticRequest, generate_agentic, install_agentic_bridge
from integrations.deeptutor.client import BackendUnavailable, DeepTutorBackend
from llm.client import LLMClient, LLMError


class AgenticContractTests(unittest.TestCase):
    def test_gateway_requires_token_and_rejects_extra_fields(self):
        app = FastAPI(); install_agentic_bridge(app)
        payload = dict(model='test', messages=[{'role': 'user', 'content': '教材问题'}], evidence='[1] 原文', max_characters=500)
        with TestClient(app) as client, patch.dict(os.environ, DEEPTUTOR_BRIDGE_TOKEN='x' * 32):
            self.assertEqual(client.post('/internal/heart/agentic', json=payload).status_code, 401)
            headers = {'X-Heart-Bridge-Token': 'x' * 32}
            for extra in ({'tools': ['exec']}, {'api_key': 'secret'}, {'evidence': ''}, {'max_tokens': 100}):
                self.assertEqual(client.post('/internal/heart/agentic', json=payload | extra, headers=headers).status_code, 422)

    def test_only_explicit_teaching_calls_use_loop(self):
        llm = LLMClient(api_key='fixture-key', mock=False)
        with patch.dict(os.environ, DEEPTUTOR_LLM_ENABLED='1', DEEPTUTOR_AGENTIC_ENABLED='1'), patch.object(DeepTutorBackend, 'generate', return_value=('回答', 'stop')) as generate:
            llm.chat([{'role': 'user', 'content': '讲解'}], agentic_evidence='[1] 教材', agentic_max_characters=260)
            self.assertEqual(generate.call_args.kwargs['evidence'], '[1] 教材')
            self.assertEqual(generate.call_args.kwargs['max_characters'], 260)
            llm.chat([{'role': 'user', 'content': '质检 JSON'}])
            self.assertNotIn('evidence', generate.call_args.kwargs)
        with patch.dict(os.environ, DEEPTUTOR_LLM_ENABLED='0', DEEPTUTOR_AGENTIC_ENABLED='1'), patch.object(llm, '_client_lazy') as old:
            with self.assertRaises(LLMError): llm.chat([{'role': 'user', 'content': 'x'}], agentic_evidence='教材')
            old.assert_not_called()

    def test_backend_verifies_evidence_receipt(self):
        backend = DeepTutorBackend()
        receipt = {'content': '回答', 'finish_reason': 'stop', 'engine': 'agent_loop', 'evidence_reads': 1, 'rounds': 2, 'tool_steps': 1,
            'evidence_sha256': hashlib.sha256('本轮教材'.encode()).hexdigest()}
        with patch.object(backend, '_post', return_value=receipt) as post:
            self.assertEqual(backend.generate([], model='test', temperature=.2, max_tokens=300, evidence='本轮教材'), ('回答', 'stop'))
            self.assertTrue(post.call_args.args[0].endswith('/agentic'))
        for change in ({'engine': 'mock'}, {'evidence_sha256': 'old'}, {'evidence_reads': True}, {'rounds': 1}, {'tool_steps': 0}):
            with patch.object(backend, '_post', return_value=receipt | change):
                with self.assertRaises(BackendUnavailable):
                    backend.generate([], model='test', temperature=.2, max_tokens=300, evidence='本轮教材')


class NativeLoopTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        if importlib.util.find_spec('deeptutor') is None: raise unittest.SkipTest('需要独立上游环境')

    def request(self, evidence='[1] 本轮教材，证据ID:A', **kwargs):
        return AgenticRequest(model='test-model', evidence=evidence, max_characters=kwargs.pop('max_characters', 500),
            messages=[{'role': 'system', 'content': '只给提示，不许泄露答案'},
                {'role': 'user', 'content': '帮我理解教材'}], **kwargs)

    @staticmethod
    def chunk(delta, reason):
        from openai.types.chat import ChatCompletionChunk
        return ChatCompletionChunk(id='fixture', created=1, model='test-model', object='chat.completion.chunk',
            choices=[{'index': 0, 'delta': delta, 'finish_reason': reason}])

    async def run_native(self, request, create):
        from deeptutor.agents.chat.agentic_pipeline import AgenticChatPipeline
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with patch.dict(os.environ, DEEPSEEK_API_KEY='fixture', DEEPSEEK_MODEL='test-model'), \
                patch.object(AgenticChatPipeline, '_build_openai_client', return_value=client):
            return await generate_agentic(request)

    async def test_real_loop_dispatches_and_hides_draft_and_reasoning(self):
        requests = []

        async def create(**kwargs):
            requests.append(deepcopy(kwargs))
            async def chunks():
                if len(requests) == 1:
                    yield self.chunk({'content': '不应发布的过程草稿', 'tool_calls': [{'index': 0, 'id': 'evidence-1', 'type': 'function',
                        'function': {'name': 'read_current_evidence', 'arguments': '{}'}}]}, 'tool_calls')
                else:
                    yield self.chunk({'content': '<think>秘密推理</think>只给一个提示。[1]'}, 'stop')
            return chunks()

        request = self.request()
        before = deepcopy(request.messages)
        result = await self.run_native(request, create)
        self.assertEqual(result['content'], '只给一个提示。[1]')
        self.assertEqual((result['engine'], result['rounds'], result['tool_steps'], result['evidence_reads']), ('agent_loop', 2, 1, 1))
        self.assertEqual(request.messages, before)
        self.assertEqual([row['content'] for row in requests[1]['messages'] if row['role'] == 'tool'], [request.evidence])
        self.assertEqual([tool['function']['name'] for tool in requests[0]['tools']], ['read_current_evidence'])
        self.assertEqual(requests[0]['tool_choice'], {'type': 'function', 'function': {'name': 'read_current_evidence'}})
        self.assertIn(before[0], requests[0]['messages'])

    async def test_answer_without_reading_evidence_is_rejected(self):
        async def create(**kwargs):
            async def chunks(): yield self.chunk({'content': '未经工具核验的答案'}, 'stop')
            return chunks()
        with self.assertRaises(HTTPException) as failure: await self.run_native(self.request(), create)
        self.assertEqual(failure.exception.status_code, 502)

    async def test_provider_rejection_never_strips_images_or_tools(self):
        create = AsyncMock(side_effect=RuntimeError('image input unsupported; private-key'))
        request = self.request()
        import base64
        request.messages[-1]['content'] = [{'type': 'text', 'text': '原公式'},
            {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode()}}]
        with self.assertRaises(HTTPException) as failure: await self.run_native(request, create)
        self.assertNotIn('private', failure.exception.detail)
        self.assertEqual(create.await_count, 1)
        self.assertTrue(create.call_args.kwargs['tools'])
        self.assertTrue(any(isinstance(row['content'], list) for row in create.call_args.kwargs['messages']))

    async def test_two_students_have_separate_evidence_and_scoped_config_resets(self):
        from deeptutor.services.llm.config import _SCOPED_LLM_CONFIG
        seen = []
        async def create(**kwargs):
            tools = [row['content'] for row in kwargs['messages'] if row['role'] == 'tool']
            async def chunks():
                await asyncio.sleep(0)
                if not tools:
                    yield self.chunk({'tool_calls': [{'index': 0, 'id': 'read', 'type': 'function',
                        'function': {'name': 'read_current_evidence', 'arguments': '{}'}}]}, 'tool_calls')
                else:
                    seen.append(tools)
                    yield self.chunk({'content': tools[0]}, 'stop')
            return chunks()
        before = _SCOPED_LLM_CONFIG.get()
        results = await asyncio.gather(self.run_native(self.request('学生A教材'), create), self.run_native(self.request('学生B教材'), create))
        self.assertEqual({result['content'] for result in results}, {'学生A教材', '学生B教材'})
        self.assertEqual(sorted(seen), [['学生A教材'], ['学生B教材']])
        self.assertIs(_SCOPED_LLM_CONFIG.get(), before)

    async def test_deadline_cancels_provider_and_resets_scope(self):
        from deeptutor.services.llm.config import _SCOPED_LLM_CONFIG
        before = _SCOPED_LLM_CONFIG.get()
        cancelled = asyncio.Event()
        async def create(**kwargs):
            try: await asyncio.Event().wait()
            finally: cancelled.set()
        with self.assertRaises(HTTPException): await self.run_native(self.request(timeout=1), create)
        self.assertTrue(cancelled.is_set())
        self.assertIs(_SCOPED_LLM_CONFIG.get(), before)

    async def test_endless_tools_have_a_hard_request_bound(self):
        calls = []
        async def create(**kwargs):
            calls.append(kwargs)
            async def chunks():
                yield self.chunk({'tool_calls': [{'index': 0, 'id': str(len(calls)), 'type': 'function',
                    'function': {'name': 'read_current_evidence', 'arguments': '{}'}}]}, 'tool_calls')
            return chunks()
        with self.assertRaises(HTTPException): await self.run_native(self.request(), create)
        self.assertLessEqual(len(calls), 6)

    async def test_unknown_tool_cannot_reach_global_registry(self):
        from deeptutor.runtime.registry.tool_registry import get_tool_registry
        global_registry = get_tool_registry()
        calls = 0
        async def create(**kwargs):
            nonlocal calls
            calls += 1
            async def chunks():
                if calls == 1:
                    yield self.chunk({'tool_calls': [{'index': 0, 'id': 'bad-tool', 'type': 'function',
                        'function': {'name': 'exec', 'arguments': '{"command":"whoami"}'}}]}, 'tool_calls')
                else:
                    yield self.chunk({'content': '伪造已经执行成功'}, 'stop')
            return chunks()
        with patch.object(global_registry, 'execute', new_callable=AsyncMock) as execute:
            with self.assertRaises(HTTPException): await self.run_native(self.request(), create)
            execute.assert_not_awaited()

    async def test_failure_after_evidence_cannot_publish_salvaged_text(self):
        calls = 0
        async def create(**kwargs):
            nonlocal calls
            calls += 1
            if calls > 1: raise RuntimeError('connection dropped')
            async def chunks():
                yield self.chunk({'content': '暂存草稿', 'tool_calls': [{'index': 0, 'id': 'read', 'type': 'function',
                    'function': {'name': 'read_current_evidence', 'arguments': '{}'}}]}, 'tool_calls')
            return chunks()
        with self.assertRaises(HTTPException): await self.run_native(self.request(), create)
        self.assertGreaterEqual(calls, 2)
        self.assertLessEqual(calls, 4)

    async def test_repeated_truncation_never_becomes_complete_answer(self):
        calls = 0
        async def create(**kwargs):
            nonlocal calls
            calls += 1
            async def chunks():
                if calls == 1:
                    yield self.chunk({'tool_calls': [{'index': 0, 'id': 'read', 'type': 'function',
                        'function': {'name': 'read_current_evidence', 'arguments': '{}'}}]}, 'tool_calls')
                else:
                    yield self.chunk({'content': '未完成的讲解'}, 'length')
            return chunks()
        with self.assertRaises(HTTPException): await self.run_native(self.request(), create)
        self.assertLessEqual(calls, 6)


    async def test_native_finish_guard_rewrites_overlong_draft(self):
        calls = []
        async def create(**kwargs):
            calls.append(deepcopy(kwargs))
            async def chunks():
                if len(calls) == 1:
                    yield self.chunk({'tool_calls': [{'index': 0, 'id': 'read', 'type': 'function',
                        'function': {'name': 'read_current_evidence', 'arguments': '{}'}}]}, 'tool_calls')
                else:
                    yield self.chunk({'content': '过长草稿' * 30 if len(calls) == 2 else '简短且完整。[1]'}, 'stop')
            return chunks()
        result = await self.run_native(self.request(max_characters=50), create)
        self.assertEqual(result['content'], '简短且完整。[1]')
        self.assertEqual(result['rounds'], 3)
        self.assertTrue(any('草稿超过本轮50字' in str(row['content']) for row in calls[-1]['messages']))

    async def test_native_transport_retry_preserves_tool_requirement(self):
        calls = []
        async def create(**kwargs):
            calls.append(deepcopy(kwargs))
            if len(calls) == 1: raise ConnectionError('transient socket failure')
            async def chunks():
                if len(calls) == 2:
                    yield self.chunk({'tool_calls': [{'index': 0, 'id': 'read', 'type': 'function',
                        'function': {'name': 'read_current_evidence', 'arguments': '{}'}}]}, 'tool_calls')
                else:
                    yield self.chunk({'content': '已核验提示。[1]'}, 'stop')
            return chunks()
        result = await self.run_native(self.request(), create)
        self.assertEqual(result['content'], '已核验提示。[1]')
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0]['messages'], calls[1]['messages'])
        self.assertEqual(calls[0]['tools'], calls[1]['tools'])
        self.assertEqual(calls[0]['tool_choice'], calls[1]['tool_choice'])


if __name__ == '__main__': unittest.main()
