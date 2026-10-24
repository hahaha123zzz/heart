import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from llm.client import LLMClient


class ToolProviderCompatibility(unittest.TestCase):
    def test_deepseek_forced_tool_mode_matches_stream_options(self):
        client = LLMClient(api_key='synthetic', base_url='https://api.deepseek.com', mock=False)
        client._client = Mock()
        client._client.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content='', tool_calls=[]), finish_reason='stop')], usage=None)
        client.chat_with_tools([{'role':'user','content':'test'}], [{'type':'function'}], tool_choice='required')
        arguments = client._client.chat.completions.create.call_args.kwargs
        self.assertEqual(arguments['extra_body'], {'thinking': {'type':'disabled'}})
        self.assertEqual(arguments['tool_choice'], 'required')

    def test_other_provider_does_not_receive_deepseek_options(self):
        client = LLMClient(api_key='synthetic', base_url='https://example.test/v1', mock=False)
        client._client = Mock()
        client._client.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content='ok', tool_calls=[]), finish_reason='stop')], usage=None)
        client.chat_with_tools([{'role':'user','content':'test'}], [])
        self.assertNotIn('extra_body', client._client.chat.completions.create.call_args.kwargs)
