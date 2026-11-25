"""学生聊天未显式配置时，请求里不得再补回项目固定输出上限。"""
import os
import unittest
from unittest.mock import patch


class AnswerBudgetDefaultTests(unittest.TestCase):
    def test_host_helper_has_no_project_default(self):
        from llm.client import answer_max_tokens
        with patch.dict(os.environ, {"ANSWER_MAX_TOKENS": ""}):
            self.assertIsNone(answer_max_tokens())
        with patch.dict(os.environ, {"ANSWER_MAX_TOKENS": "12000"}):
            self.assertEqual(answer_max_tokens(), 12000)

    def test_agentic_request_defaults_to_provider_choice(self):
        from integrations.deeptutor.agentic_bridge import AgenticRequest
        request = AgenticRequest(messages=[{"role": "user", "content": "你好"}],
                                 model="deepseek-chat", evidence="证据")
        self.assertIsNone(request.max_tokens)

    def test_completion_kwargs_omit_unset_budget(self):
        from deeptutor.runtime.agentic.client import build_completion_kwargs
        kwargs = build_completion_kwargs(temperature=0.2, model="deepseek-chat", max_tokens=None)
        self.assertNotIn("max_tokens", kwargs)
        self.assertNotIn("max_completion_tokens", kwargs)

    def test_completion_kwargs_keep_an_explicit_budget(self):
        from deeptutor.runtime.agentic.client import build_completion_kwargs
        kwargs = build_completion_kwargs(temperature=0.2, model="deepseek-chat", max_tokens=12000)
        self.assertEqual(kwargs["max_tokens"], 12000)

    def test_provider_bodies_omit_unset_budget(self):
        from deeptutor.services.llm.provider_core.openai_compat_provider import (
            OpenAICompatProvider,
        )
        provider = OpenAICompatProvider.__new__(OpenAICompatProvider)
        provider._spec = None
        provider.default_model = "deepseek-chat"
        chat = provider._build_kwargs([{"role": "user", "content": "hi"}], None, "deepseek-chat",
                                      None, 0.2, None, None)
        self.assertNotIn("max_tokens", chat)
        self.assertNotIn("max_completion_tokens", chat)
        body = provider._build_responses_body([{"role": "user", "content": "hi"}], None,
                                              "deepseek-chat", None, 0.2, None, None)
        self.assertNotIn("max_output_tokens", body)

    def test_pipeline_default_stage_budget_is_unset(self):
        from deeptutor.agents.loop.pipeline import _read_int
        from deeptutor.services.config.loader import DEFAULT_CHAT_PARAMS
        self.assertIsNone(_read_int({}, key="max_tokens", default=None))
        self.assertIsNone(DEFAULT_CHAT_PARAMS["responding"]["max_tokens"])


if __name__ == "__main__":
    unittest.main()
