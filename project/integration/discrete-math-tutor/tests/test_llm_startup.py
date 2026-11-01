"""SDK imports complete before readiness, without making a model request."""
import asyncio
import os
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from memory.background_worker import memory_lifespan


class ModelStartupTests(unittest.TestCase):
    def test_sdk_preparation_is_only_for_configured_local_real_model(self):
        for mock, key, remote, expected in (
            (False, 'synthetic-key', '0', 1), (True, 'synthetic-key', '0', 0),
            (False, '', '0', 0), (False, 'synthetic-key', '1', 0),
        ):
            with self.subTest(mock=mock, configured=bool(key), remote=remote):
                client = SimpleNamespace(mock=mock, api_key=key)
                app = SimpleNamespace(state=SimpleNamespace(memory_llm=client))
                prepare = Mock()
                async def run():
                    async with memory_lifespan(app):
                        self.assertEqual(prepare.call_count, expected)
                with patch.dict(os.environ, MEMORY_WORKER_ENABLED='0', DEEPTUTOR_LLM_ENABLED=remote), \
                     patch('memory.background_worker.import_module', prepare, create=True), \
                     patch('knowledge.fixed_book.start', new_callable=AsyncMock), \
                     patch('knowledge.fixed_book.stop', new_callable=AsyncMock), \
                     patch('llm.transport.close_pool'):
                    asyncio.run(run())
                if expected:
                    prepare.assert_called_once_with('openai')


if __name__ == '__main__':
    unittest.main()
