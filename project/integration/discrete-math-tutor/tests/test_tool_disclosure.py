"""按需工具分层：清单保留名称，schema 加载后才发送。"""
import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from deeptutor.agents.loop import pipeline as module
from deeptutor.core.context import UnifiedContext
from deeptutor.core.tool_protocol import ToolResult
from deeptutor.runtime.registry.tool_registry import ToolRegistry
from integrations.deeptutor import tool_disclosure
from integrations.deeptutor.tool_policy import teaching_tool_scope


class ToolDisclosureTests(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry()
        self.registry.load_builtins()
        self.pipeline = SimpleNamespace(
            tool_lookup=self.registry,
            language='zh',
            _deferred_loader=None,
            _is_partner_turn=lambda ctx: False,
            _coexisting_rag_kbs=lambda ctx: [],
            _mastery_nav_available=lambda ctx: False,
            _capability_owned_tools=lambda ctx: (),
            _exclusive_capability_active=lambda ctx: False,
        )
        self.patches = [patch.multiple(
            module,
            user_has_memory=lambda: False,
            user_has_notebooks=lambda: False,
            user_has_question_bank=lambda: False,
            partner_can_record_questions=lambda: False,
        )]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        tool_disclosure._LOADER.set(None)

    def _turn(self):
        return teaching_tool_scope()

    def test_catalog_turn_lists_kb_files_but_sends_schema_only_after_load(self):
        context = UnifiedContext(user_message='教材目录')
        with self._turn():
            names = module.AgenticLoopPipeline._compose_enabled_tools(self.pipeline, context)
            self.assertIn('kb_files', names)
            self.assertIn('load_tools', names)
            schemas = module.AgenticLoopPipeline._build_llm_tool_schemas(
                self.pipeline, names, context)
            sent = {item['function']['name'] for item in schemas}
            self.assertNotIn('kb_files', sent)
            self.assertIn('load_tools', sent)
            manifest = module.AgenticLoopPipeline._tool_manifest(self.pipeline, names)
            self.assertIn('按需工具', manifest)
            self.assertIn('`kb_files`', manifest)

            loader = tool_disclosure.current_loader()
            self.assertIsNotNone(loader)
            self.assertEqual(loader.load(['kb_files'])['loaded'], ['kb_files'])
            self.assertIn('kb_files', {item['function']['name'] for item in schemas})
            self.assertEqual(loader.load(['kb_files'])['already_loaded'], ['kb_files'])
            self.assertEqual(loader.load(['rag'])['unknown'], ['rag'])

    def test_unloaded_on_demand_tool_is_refused_at_execution(self):
        context = UnifiedContext(user_message='教材目录')
        tool = self.registry.get('kb_files')
        with self._turn(), patch.object(tool, 'execute', new=AsyncMock(return_value=ToolResult(content='目录'))):
            module.AgenticLoopPipeline._compose_enabled_tools(self.pipeline, context)
            refused = asyncio.run(self.registry.execute('kb_files'))
            self.assertFalse(refused.success)
            self.assertIn('load_tools', refused.content)

            loader = tool_disclosure.current_loader()
            self.assertIsNotNone(loader)
            loader.load(['kb_files'])
            self.assertTrue(asyncio.run(self.registry.execute('kb_files')).success)

    def test_common_retrieval_tools_stay_direct(self):
        context = UnifiedContext(user_message='自变量是什么')
        with self._turn():
            names = module.AgenticLoopPipeline._compose_enabled_tools(self.pipeline, context)
            self.assertTrue({'rag', 'read_source'} <= set(names))
            self.assertNotIn('load_tools', names)
            sent = {item['function']['name'] for item in
                    module.AgenticLoopPipeline._build_llm_tool_schemas(self.pipeline, names, context)}
            self.assertTrue({'rag', 'read_source'} <= sent)

    def test_reading_keeps_goto_direct_and_loads_auxiliary_tools(self):
        self.pipeline._capability_owned_tools = lambda ctx: (
            'reading_list_tabs', 'reader_goto', 'read_material')
        context = UnifiedContext(user_message='继续读这一页')
        with self._turn():
            names = module.AgenticLoopPipeline._compose_enabled_tools(self.pipeline, context)
            self.assertIn('load_tools', names)
            sent = {item['function']['name'] for item in
                    module.AgenticLoopPipeline._build_llm_tool_schemas(self.pipeline, names, context)}
            self.assertIn('reader_goto', sent)
            self.assertIn('read_material', sent)
            self.assertNotIn('reading_list_tabs', sent)

    def test_next_turn_starts_without_the_previous_loads(self):
        catalog = UnifiedContext(user_message='教材目录')
        with self._turn():
            module.AgenticLoopPipeline._compose_enabled_tools(self.pipeline, catalog)
            self.assertIsNotNone(tool_disclosure.current_loader())
            greeting = UnifiedContext(user_message='你好')
            names = module.AgenticLoopPipeline._compose_enabled_tools(self.pipeline, greeting)
            self.assertIsNone(tool_disclosure.current_loader())
            self.assertNotIn('kb_files', names)

    def test_load_tools_is_allowed_for_students(self):
        from integrations.deeptutor.product_surface import validate_options
        validate_options({'capability': 'chat', 'tools': ['load_tools']})


if __name__ == '__main__':
    unittest.main()
