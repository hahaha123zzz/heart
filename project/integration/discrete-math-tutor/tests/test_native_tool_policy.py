from contextlib import closing
"""验证工具隐藏覆盖发现、schema、延迟工具与执行，且不污染其他上下文。"""
import asyncio
import unittest

from integrations.deeptutor.tool_policy import teaching_tool_scope, hidden_names, HIDDEN_EXTENSIONS
from deeptutor.runtime.registry.tool_registry import ToolRegistry


class NativeToolPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_scope_filters_discovery_schemas_and_execution_and_restores(self):
        registry = ToolRegistry(); registry.load_builtins()
        self.assertEqual(len(registry.list_tools()), 100)
        self.assertEqual(len(hidden_names()), 31)
        for name in ('ask_user','rag','workspace_list','reason','read_source','solve_plan'):
            self.assertIn(name, registry.list_tools())
        with teaching_tool_scope():
            self.assertEqual(len(registry.list_tools()), 69)
            self.assertIsNone(registry.get('obsidian_read'))
            self.assertEqual(registry.build_openai_schemas(['obsidian_read','ask_user'])[0]['function']['name'],'ask_user')
            self.assertEqual(len(registry.build_openai_schemas(['obsidian_read','ask_user'])),1)
            with self.assertRaises(KeyError):await registry.execute('obsidian_read',note='private')
            async def child():
                await asyncio.sleep(0)
                return registry.get('obsidian_read')
            task=asyncio.create_task(child())
        self.assertIsNone(await task)
        self.assertIsNotNone(registry.get('obsidian_read'))
        self.assertEqual(len(registry.list_tools()),100)

    async def test_unneeded_extensions_cannot_activate_exclusive_prompts(self):
        from deeptutor.capabilities.registry import all_loop_capabilities
        with teaching_tool_scope():
            enabled=all_loop_capabilities()
            self.assertFalse({extension.name for extension in enabled} & HIDDEN_EXTENSIONS)
            self.assertEqual(len(enabled),8)
        self.assertEqual(len(all_loop_capabilities()),14)

    async def test_source_read_mount_does_not_expand_explicit_builtin_whitelist(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from deeptutor.core.context import UnifiedContext
        from deeptutor.agents.loop import pipeline as module
        registry=ToolRegistry();registry.load_builtins()
        pipeline=SimpleNamespace(tool_lookup=registry,
            _is_partner_turn=lambda ctx:False, _coexisting_rag_kbs=lambda ctx:['course'],
            _mastery_nav_available=lambda ctx:False, _capability_owned_tools=lambda ctx:(),
            _exclusive_capability_active=lambda ctx:False)
        context=UnifiedContext()
        with teaching_tool_scope(), patch.object(module,'compose_enabled_tools',return_value=['rag']), patch.multiple(module,
                user_has_memory=lambda:False,user_has_notebooks=lambda:False,
                user_has_question_bank=lambda:False,partner_can_record_questions=lambda:False):
            names=module.AgenticLoopPipeline._compose_enabled_tools(pipeline,context)
            self.assertIn('read_source',names)
            context.allowed_builtin_tools=['rag']
            restricted=module.AgenticLoopPipeline._compose_enabled_tools(pipeline,context)
            self.assertNotIn('read_source',restricted)

    async def test_host_textbook_tools_mount_without_native_kb_and_keep_stage_boundaries(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from deeptutor.core.context import UnifiedContext
        from deeptutor.agents.loop import pipeline as module
        registry=ToolRegistry();registry.load_builtins()
        pipeline=SimpleNamespace(tool_lookup=registry,
            _is_partner_turn=lambda ctx:False, _coexisting_rag_kbs=lambda ctx:[],
            _mastery_nav_available=lambda ctx:False, _capability_owned_tools=lambda ctx:(),
            _exclusive_capability_active=lambda ctx:False)
        context=UnifiedContext()
        with teaching_tool_scope(), patch.multiple(module,user_has_memory=lambda:False,
                user_has_notebooks=lambda:False,user_has_question_bank=lambda:False,partner_can_record_questions=lambda:False):
            names=module.AgenticLoopPipeline._compose_enabled_tools(pipeline,context)
            self.assertTrue({'rag','kb_files','read_source'} <= set(names))
            context.allowed_builtin_tools=['workspace_list']
            names=module.AgenticLoopPipeline._compose_enabled_tools(pipeline,context)
            self.assertFalse({'rag','kb_files','read_source'} & set(names))
            context.allowed_builtin_tools=None
            pipeline._exclusive_capability_active=lambda ctx:True
            names=module.AgenticLoopPipeline._compose_enabled_tools(pipeline,context)
            self.assertNotIn('rag',names)
            self.assertNotIn('kb_files',names)

    async def test_preloaded_deferred_tools_cannot_escape_scope(self):
        from deeptutor.core.tool_protocol import BaseTool, ToolDefinition, ToolResult
        class HiddenDeferred(BaseTool):
            deferred=True
            def get_definition(self):return ToolDefinition(name='cron',description='must be hidden')
            async def execute(self,**kwargs):raise AssertionError('hidden tool executed')
        registry=ToolRegistry(); registry.load_builtins(); registry.register(HiddenDeferred())
        self.assertEqual(len(registry.deferred_tools()),1)
        with teaching_tool_scope():
            self.assertEqual(registry.deferred_tools(),[])
            self.assertIsNone(registry.get('cron'))
            with self.assertRaises(KeyError):await registry.execute('cron')
        self.assertEqual(len(registry.deferred_tools()),1)


class CourseSourceReadTests(unittest.IsolatedAsyncioTestCase):
    async def test_rag_result_can_be_read_in_full_from_same_turn(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from deeptutor.core.context import UnifiedContext
        from deeptutor.tools.builtin import ReadSourceTool
        from integrations.deeptutor.heart_rag import HeartCourseRagTool
        context=UnifiedContext()
        import sqlite3
        from knowledge.course_config import PSYCHOLOGY_DIR
        from knowledge.hybrid_retrieval import _as_chunk
        path=PSYCHOLOGY_DIR/'rag_index.sqlite3'
        if not path.is_file():self.skipTest('需要本机正式教材索引')
        with closing(sqlite3.connect(path)) as db:
            db.row_factory=sqlite3.Row
            chunk=_as_chunk(db.execute("SELECT * FROM chunks WHERE chapter_id=2 AND text LIKE '%自变量%' ORDER BY length(text) DESC LIMIT 1").fetchone())
        text=chunk.text
        with patch('knowledge.psychology_retrieval.retrieve',return_value=[chunk]):
            result=await HeartCourseRagTool().execute(query='自变量是什么',_heart_context=context)
        self.assertTrue(result.success)
        source_id=next(iter(context.metadata['source_index']))
        self.assertIn(source_id,result.content)
        loaded=await ReadSourceTool().execute(source_id=source_id,source_index=context.metadata['source_index'])
        self.assertTrue(loaded.success)
        self.assertIn(text,loaded.content)
        other=UnifiedContext()
        rejected=await ReadSourceTool().execute(source_id=source_id,source_index=other.metadata.get('source_index'))
        self.assertFalse(rejected.success)
