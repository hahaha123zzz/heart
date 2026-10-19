"""生成边界与原模型调用契约；测试不会发送外部请求。"""
import importlib.util
import os
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from integrations.deeptutor.generation_bridge import GenerationRequest, generate, install_generation_bridge
from integrations.deeptutor.client import BackendUnavailable, DeepTutorBackend
from llm.client import LLMClient, LLMError


class GenerationContractTests(unittest.TestCase):
    def test_rejects_remote_images_keys_roles_and_tools(self):
        for message in ({"role": "tool", "content": "x"}, {"role": [], "content": "x"},
                        {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "https://example.com/private.png"}}]},
                        {"role": "user", "content": "x", "tool_calls": []}):
            with self.assertRaises(ValueError): GenerationRequest(model="test", messages=[message])
        with self.assertRaises(ValueError): GenerationRequest(model="test", messages=[{"role":"user","content":"x"}], api_key="secret")

    def test_host_routes_text_and_preserves_truncation_failure(self):
        llm = LLMClient(api_key="private", mock=False)
        messages = [{"role":"user", "content":"只给提示"}]
        with patch.dict(os.environ, DEEPTUTOR_LLM_ENABLED="1"), patch.object(DeepTutorBackend, "generate", return_value=("合格回答", "stop")) as call, patch.object(llm, "_client_lazy") as old:
            self.assertEqual(llm.chat(messages), "合格回答")
            self.assertEqual(call.call_args.args[0], messages)
            old.assert_not_called()
        with patch.dict(os.environ, DEEPTUTOR_LLM_ENABLED="1"), patch.object(DeepTutorBackend, "generate", return_value=("未完成", "length")):
            with self.assertRaises(LLMError): llm.chat(messages)

    def test_enabled_failure_does_not_fall_back_or_send_key(self):
        llm = LLMClient(api_key="private", mock=False)
        with patch.dict(os.environ, DEEPTUTOR_LLM_ENABLED="1"), patch.object(DeepTutorBackend, "generate", side_effect=BackendUnavailable("暂不可用")), patch.object(llm, "_client_lazy") as old:
            with self.assertRaises(LLMError): llm.chat([{"role":"user","content":"问题"}])
            old.assert_not_called()
        backend = DeepTutorBackend()
        with patch.object(backend, "_post", return_value={"content":"ok","finish_reason":"stop"}) as post:
            backend.generate([], model="test", temperature=.2, max_tokens=200)
        self.assertNotIn("api_key", post.call_args.args[1])

    def test_mock_stays_local(self):
        with patch.dict(os.environ, DEEPTUTOR_LLM_ENABLED="1"), patch.object(DeepTutorBackend, "generate") as call:
            LLMClient(mock=True).chat([{"role":"user","content":"你好"}])
            call.assert_not_called()

    def test_gateway_requires_host_token(self):
        app = FastAPI(); install_generation_bridge(app)
        with TestClient(app) as client, patch.dict(os.environ, DEEPTUTOR_BRIDGE_TOKEN="x"*32):
            self.assertEqual(client.post("/internal/heart/generate", json={"model":"test", "messages":[{"role":"user","content":"x"}]}).status_code, 401)


class ProviderReuseTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        if importlib.util.find_spec("deeptutor") is None: raise unittest.SkipTest("需要独立上游环境")

    async def test_isolated_provider_receives_limits_and_is_closed(self):
        provider = SimpleNamespace(chat_with_retry=AsyncMock(return_value=SimpleNamespace(content="<think>隐藏推理</think>正式回答", finish_reason="stop", reasoning_content="推理", tool_calls=[])), aclose=AsyncMock())
        request = GenerationRequest(model="test-model", messages=[{"role":"user","content":"教材问题"}], max_tokens=300, temperature=.2)
        with patch.dict(os.environ, DEEPSEEK_API_KEY="fixture-key", DEEPSEEK_MODEL="test-model", OPENAI_BASE_URL="https://api.deepseek.com"), patch("deeptutor.services.llm.provider_factory.build_isolated_provider", return_value=provider) as factory:
            result = await generate(request)
        self.assertEqual(result, {"content":"正式回答", "finish_reason":"stop"})
        self.assertEqual(factory.call_args.args[0].max_tokens, 300)
        self.assertFalse(provider.chat_with_retry.call_args.kwargs["allow_image_fallback"])
        provider.aclose.assert_awaited_once()

    async def test_provider_error_is_generic_and_closed(self):
        provider = SimpleNamespace(chat_with_retry=AsyncMock(side_effect=RuntimeError("private-key-and-prompt")), aclose=AsyncMock())
        with patch.dict(os.environ, DEEPSEEK_API_KEY="fixture-key", DEEPSEEK_MODEL="test-model"), patch("deeptutor.services.llm.provider_factory.build_isolated_provider", return_value=provider):
            with self.assertRaises(HTTPException) as raised:
                await generate(GenerationRequest(model="test-model", messages=[{"role":"user","content":"x"}]))
        self.assertNotIn("private", raised.exception.detail)
        provider.aclose.assert_awaited_once()
