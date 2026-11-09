"""统一上下文的实际消费、权限、历史重放和持久化边界。"""
import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from agents.agent_loop import LocalAgentLoop, LoopRequest
from agents.conversation_context import build_history
from agents.context_runtime.context import UnifiedContext
from agents.context_runtime.model_history import normalize_model_turn
from agents.loop_prompts import build_loop_system_prompt
from agents.q3_tools import AskUserTool
from agents.task_context_builder import TaskContextBuilder
from agents.tool_protocol import BaseTool, ToolDefinition, ToolRegistry, ToolResult
from agents.turn_context import render_turn_prompt, retained_model_turn
from llm.client import ChatToolCall, ChatToolResult


class ScriptedLLM:
    model = "deepseek-flash"
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []
    def chat_with_tools(self, messages, tools, **kwargs):
        self.calls.append((deepcopy(messages), deepcopy(tools)))
        return self.responses.pop(0)


def tool(name):
    return ChatToolResult(finish_reason="tool_calls", tool_calls=[
        ChatToolCall(id="c1", name=name, arguments={"question": "选择讲法？"})])


def final(text="解释完毕"):
    return ChatToolResult(text=text, finish_reason="stop")


class CaptureTool(BaseTool):
    definition = ToolDefinition("capture", "读取本轮上下文")
    def __init__(self):
        self.contexts = []
    def run(self, arguments, context):
        self.contexts.append(context)
        context.state["captured"] = True
        return ToolResult(content="已读取")


class UnifiedContextChainTests(unittest.TestCase):
    def context(self, **kwargs):
        return TaskContextBuilder().build(student_id="s", session_id="session", message="解释这个概念", **kwargs)

    def request(self, context, registry):
        return LoopRequest(student_id="s", session_id="session", task_id="task", request_id="r",
            message=context.user_message, system_prompt="教学规则", tools=registry, context=context)

    def test_builder_and_task_share_context_without_serializing_runtime(self):
        task = self.context(history=[{"role": "user", "content": "前问"}, {"role": "assistant", "content": "前答"}])
        context = task.unified_context
        self.assertIs(task.unified_context, context)
        self.assertEqual(context.runtime.model_history[-1]["content"], "前答")
        context.extension("heart")["private_callback"] = lambda: None
        json.dumps(task.model_dump(), ensure_ascii=False)
        self.assertNotIn("private_callback", task.model_dump_json())
        self.assertGreater(context.metadata["history_budget"], 0)

    def test_native_history_preserves_long_message_and_more_than_40_rows(self):
        rows = [{"role": "user", "content": "问题"}, {"role": "assistant", "content": "长回答" * 1800}]
        result = build_history(rows, budget_tokens=1)
        self.assertEqual(result.history, rows)
        many = [{"role": role, "content": str(i)} for i in range(30) for role in ("user", "assistant")]
        task = self.context(history=many)
        self.assertEqual(len(task.history), 60)

    def test_native_history_replays_complete_tool_exchange(self):
        exchange = [{"role": "user", "content": "查来源"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "old", "type": "function",
                "function": {"name": "retrieve_course", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "old", "content": "历史教材"},
            {"role": "assistant", "content": "旧答案"}]
        task = self.context(history=[{"role": "user", "content": "查来源"},
            {"role": "assistant", "content": "旧答案", "metadata": {
                "model_turn": {"version": 1, "messages": exchange}}}])
        llm = ScriptedLLM(final())
        LocalAgentLoop(llm).run(self.request(task.unified_context, ToolRegistry()))
        sent = llm.calls[0][0]
        self.assertEqual(sum(row.get("role") == "tool" for row in sent), 1)
        self.assertEqual(sum(row.get("content") == "查来源" for row in sent), 1)

    def test_tool_and_loop_use_same_context_and_mutable_namespace(self):
        context = self.context().unified_context
        capture = CaptureTool()
        registry = ToolRegistry(); registry.register(capture)
        llm = ScriptedLLM(tool("capture"), final())
        result = LocalAgentLoop(llm).run(self.request(context, registry))
        self.assertTrue(result.completed, result.error)
        self.assertIs(result.context, context)
        self.assertIsNone(context.enabled_tools)
        self.assertIs(capture.contexts[0].unified, context)
        self.assertIs(capture.contexts[0].state, context.extension("heart")["tool_state"])
        self.assertTrue(context.extension("heart")["tool_state"]["captured"])
        self.assertEqual(context.capability_output.agent_output, result.final_text)
        budget = context.metadata["context_budget"]
        self.assertGreater(budget["used_tokens"], 0)
        self.assertEqual(budget["used_tokens"], sum(item["tokens"] for item in budget["segments"]))

    def test_empty_tool_allowlist_blocks_dispatch_as_well_as_model_schema(self):
        context = self.context().unified_context
        context.enabled_tools = []
        capture = CaptureTool()
        registry = ToolRegistry(); registry.register(capture)
        llm = ScriptedLLM(tool("capture"), final())
        result = LocalAgentLoop(llm).run(self.request(context, registry))
        self.assertTrue(result.completed, result.error)
        self.assertEqual(llm.calls[0][1], [])
        self.assertEqual(capture.contexts, [])

    def test_rejects_cross_student_or_cross_session_context(self):
        context = self.context().unified_context
        context.extension("heart")["student_id"] = "other"
        with self.assertRaises(ValueError):
            self.request(context, ToolRegistry())
        context.extension("heart")["student_id"] = "s"
        context.session_id = "other-session"
        with self.assertRaises(ValueError):
            self.request(context, ToolRegistry())

    def test_native_assembler_consumes_skills_sources_and_runtime_context(self):
        context = self.context().unified_context
        context.memory_context = "已有记忆"
        context.skills_manifest = "read_skill: 教学技能"
        context.source_manifest = "source-1: 教材"
        context.runtime.workspace = None
        base = build_loop_system_prompt(target=None, definitions=[], context=context)
        prompt = render_turn_prompt(context, base + "\n本轮追加规则")
        for text in ("已有记忆", "read_skill", "source-1", "本轮追加规则", "runtime_context"):
            self.assertIn(text, prompt)
        self.assertNotIn("student_id", prompt)
        self.assertEqual(sum(block.name == "tools" for block in context.extension("heart")["prompt_blocks"]), 1)

    def test_pause_resume_retains_protocol_and_exposes_user_answer_in_context(self):
        registry = ToolRegistry(); registry.register(AskUserTool())
        context = self.context().unified_context
        llm = ScriptedLLM(tool("ask_user"), final("按回答继续解释"))
        loop = LocalAgentLoop(llm)
        first = loop.run(self.request(context, registry))
        self.assertTrue(first.paused, first.error)
        self.assertFalse(context.interaction.end_loop)
        second = loop.run(self.request(context, registry), resume_state=first.state(), answer="用例子")
        self.assertTrue(second.completed, second.error)
        self.assertTrue(context.interaction.end_loop)
        self.assertEqual(context.interaction.user_answers[-1]["reply"], "用例子")
        self.assertIn("用例子", str(llm.calls[-1][0]))

    def test_only_current_turn_is_retained_and_private_answer_arguments_are_removed(self):
        context = self.context(history=[{"role": "user", "content": "旧问题"},
            {"role": "assistant", "content": "旧回答"}]).unified_context
        llm = ScriptedLLM(final())
        result = LocalAgentLoop(llm).run(self.request(context, ToolRegistry()))
        record = retained_model_turn(result.state())
        self.assertEqual([row["content"] for row in record["messages"]], [context.user_message, "解释完毕"])
        state = {"model_turn_start": 1, "messages": [{"role": "system", "content": "规则"},
            {"role": "assistant", "tool_calls": [{"id": "p", "function": {"name": "quiz",
                "arguments": '{"expected_answer":"私有答案","prompt":"题干"}'}}]},
            {"role": "tool", "tool_call_id": "p", "content": "已登记"}]}
        self.assertNotIn("私有答案", json.dumps(retained_model_turn(state), ensure_ascii=False))

    def test_compressed_summary_watermark_is_reused_without_calling_summarizer(self):
        rows = [{"id": 11, "role": "user", "content": "旧问题"},
            {"id": 12, "role": "assistant", "content": "旧回答"},
            {"id": 13, "role": "user", "content": "新问题"},
            {"id": 14, "role": "assistant", "content": "新回答", "metadata": {"context_summary": {
                "compressed_summary": "之前的摘要", "summary_up_to_msg_id": 12}}}]
        def fail(_rows):
            self.fail("已压缩的材料不应重新请求摘要")
        result = build_history(rows, summarizer=fail)
        self.assertEqual(result.summary, "之前的摘要")
        self.assertEqual([row["content"] for row in result.history], ["新问题", "新回答"])
        self.assertEqual(result.summary_up_to_msg_id, 12)

    def test_rolled_back_watermark_is_discarded(self):
        rows = [{"id": 21, "role": "user", "content": "当前分支"},
            {"id": 22, "role": "assistant", "content": "当前回答", "metadata": {"context_summary": {
                "compressed_summary": "其他分支摘要", "summary_up_to_msg_id": 12}}}]
        result = build_history(rows)
        self.assertEqual(result.summary, "")
        self.assertNotIn("其他分支摘要", str(result.model_history))

    def test_sync_history_builder_works_inside_running_event_loop(self):
        async def build():
            return build_history([{"role": "user", "content": "问题"}])
        self.assertEqual(asyncio.run(build()).history[0]["content"], "问题")

    def test_native_summary_uses_host_model_and_advances_watermark_only_on_success(self):
        class SummaryLLM:
            model = "deepseek-flash"
            def __init__(self): self.calls = []
            def chat(self, messages, **kwargs):
                self.calls.append((messages, kwargs))
                return "学生目标：继续理解随机分配。"
        rows = [{"role": role, "content": f"第{i}轮随机分配问题" * 5}
                for i in range(8) for role in ("user", "assistant")]
        llm = SummaryLLM()
        result = build_history(rows, budget_tokens=100, llm=llm)
        self.assertEqual(len(llm.calls), 1)
        self.assertIn("随机分配", result.summary)
        self.assertGreater(result.summary_up_to_msg_id, 0)
        self.assertEqual(result.history[-1], rows[-1])

    def test_failed_summary_retains_latest_turn_without_advancing_watermark(self):
        from llm.client import LLMError
        class FailedLLM:
            model = "deepseek-flash"
            def chat(self, *args, **kwargs): raise LLMError("离线摘要失败")
        rows = [{"role": role, "content": str(i) * 40}
                for i in range(8) for role in ("user", "assistant")]
        original = deepcopy(rows)
        result = build_history(rows, budget_tokens=30, llm=FailedLLM())
        self.assertEqual(result.summary_up_to_msg_id, 0)
        self.assertEqual(result.summary, "")
        self.assertEqual(result.history[-2:], rows[-2:])
        self.assertEqual(rows, original)

    def test_upstream_source_manifest_has_no_unused_missing_files(self):
        root = Path(__file__).parents[1]
        manifest = json.loads((root / "agents/context_runtime/SOURCE_NOTICE.json").read_text(encoding="utf-8"))
        for item in manifest["files"]:
            path = root / item["target"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), item["local_sha256"], str(path))
            self.assertNotIn("from deeptutor.", path.read_text(encoding="utf-8"))


class UnifiedContextPersistenceTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from database import database as db
        from database.models import Base
        import database.q5_learning
        from memory.memory_manager import MemoryManager
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = create_engine("sqlite:///" + self.temp.name.replace("\\", "/") + "/context.db")
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        database_patch = patch.object(db, "SessionLocal", sessionmaker(bind=self.engine, expire_on_commit=False))
        database_patch.start(); self.addCleanup(database_patch.stop)
        self.memory = MemoryManager(); self.memory.ensure_student("s", account_type="test")

    def test_private_model_history_is_scoped_and_never_returned_by_public_history(self):
        record = {"version": 1, "messages": [{"role": "user", "content": "问题"},
                    {"role": "assistant", "content": "回答"}]}
        self.memory.append("s", "user", "问题", session_id="one")
        self.memory.append("s", "assistant", "回答", session_id="one", selection_ref={
            "_model_turn": record, "_context_summary": {"compressed_summary": "摘要", "summary_up_to_msg_id": 0}})
        private = self.memory.get_history("s", session_id="one", for_context=True)
        self.assertEqual(private[-1]["metadata"]["model_turn"], record)
        self.assertEqual(self.memory.get_history("s", session_id="two", for_context=True), [])
        self.assertEqual(self.memory.get_history("other", session_id="one", for_context=True), [])
        public = self.memory.repo.get_conversation_with_figures("s", session_id="one")
        self.assertNotIn("_model_turn", str(public))
        self.assertNotIn("_context_summary", str(public))
        self.assertNotIn("metadata", str(self.memory.get_history("s", session_id="one")))

    def test_private_context_never_enters_learning_events_or_memory_index(self):
        from sqlalchemy import select
        from database.models import LearningEventRow
        record = {"version": 1, "system": "PRIVATE_MODEL_ONLY", "messages": [
            {"role": "user", "content": "问题"}, {"role": "assistant", "content": "回答"}]}
        self.memory.append_exchange("s", "问题", "回答", selection_ref={
            "section_title": "概念", "_model_turn": record}, session_id="session")
        with self.engine.connect() as connection:
            events = connection.execute(select(LearningEventRow.payload)).all()
        self.assertNotIn("PRIVATE_MODEL_ONLY", str(events))
        self.memory.repo.sync_memory_index("s")
        self.assertNotIn("PRIVATE_MODEL_ONLY", str(self.memory.repo.memory_documents("s")))
        private = self.memory.get_history("s", session_id="session", for_context=True)
        self.assertIn("PRIVATE_MODEL_ONLY", str(private))

    def test_forgetting_preference_invalidates_only_owners_derived_context(self):
        self.memory.set_preferences("s", {"answer_length": .5})
        record = {"version": 1, "messages": [{"role": "assistant", "content": "回答"}]}
        reference = {"_model_turn": record,
            "_context_summary": {"compressed_summary": "旧偏好", "summary_up_to_msg_id": 0}}
        self.memory.append("s", "assistant", "回答", session_id="session", selection_ref=reference)
        self.memory.ensure_student("other", account_type="test")
        self.memory.append("other", "assistant", "其他回答", session_id="session", selection_ref=reference)
        self.memory.forget_preference("s", "answer_length")
        own = self.memory.get_history("s", session_id="session", for_context=True)
        other = self.memory.get_history("other", session_id="session", for_context=True)
        self.assertNotIn("metadata", str(own))
        self.assertIn("context_summary", str(other))

    def test_actual_task_entry_reads_teaching_skills_then_persists_and_replays_context(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from agents.task_service import TaskService
        from agents.agent_loop_service import run_agent_loop_turn
        from agents.q3_navigation import StubLearningNavigator
        from database.learning_tasks import LearningTaskRepository
        from models.chat_request import ChatRequest
        guide = ChatToolResult(finish_reason="tool_calls", tool_calls=[ChatToolCall(
            id="guide", name="read_skill", arguments={"name": "teaching-skills", "file": "SKILL.md"})])
        llm = ScriptedLLM(guide, final("SKILLS_READY"), final("上下文已接通。"))
        policy = Mock(); policy.enabled.return_value = True; policy.can_clarify.return_value = True
        orchestrator = SimpleNamespace(llm=llm, memory=self.memory, quality_checker=None)
        service = TaskService(orchestrator, repository=LearningTaskRepository(), policy=policy)
        consumed = []
        # 执行 main.py 的真实分发函数；避免导入 main 时触发正式数据库初始化。
        import ast, os
        source = Path(__file__).parents[1] / "main.py"
        function = next(node for node in ast.parse(source.read_text(encoding="utf-8")).body
                        if isinstance(node, ast.FunctionDef) and node.name == "_execute_task_turn")
        namespace = {"orchestrator": orchestrator, "os": os}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
        def local_turn(**kwargs):
            return run_agent_loop_turn(**kwargs, navigator=StubLearningNavigator(),
                publish_gate=lambda text, result: (True, ""), llm=llm)
        def execute(request, context, resolved, intercept, guard, progress, **kwargs):
            consumed.append(context.unified_context)
            return namespace["_execute_task_turn"](request, context, resolved, intercept, guard, progress, **kwargs)
        with patch("agents.agent_loop_service.run_agent_loop_turn", local_turn), patch.dict("os.environ", {
                "LOCAL_AGENT_LOOP_ENABLED": "1", "SELECTED_TEXT_AGENT_LOOP_ENABLED": "0",
                "ADAPTIVE_TUTORING_ENABLED": "0", "Q5_LEARNING_ENABLED": "0",
                "RESPONSE_COMPOSITION_ENABLED": "0", "RESPONSE_BLOCK_STREAMING_ENABLED": "0"}):
            result = service.run(ChatRequest(student_id="s", session_id="session", request_id="native-context",
                message="解释一个概念"), execute)
            self.assertEqual(result["answer_status"], "answered", result)
            context = consumed[0]
            self.assertEqual(context.capability_output.agent_output, result["reply"])
            self.assertTrue(context.capability_output.answer_published)
            self.assertTrue(result["teaching_skills"])
            self.assertIn("skills", {block.name for block in context.extension("heart")["prompt_blocks"]})
            self.assertIsNotNone(context.metadata["context_budget"])
            next_context, _, _ = service._context(ChatRequest(student_id="s", session_id="session",
                message="继续", request_id="native-context-next"))
        replay = next_context.unified_context.runtime.model_history
        self.assertIn("上下文已接通", str(replay))
        self.assertIsNotNone(next_context.unified_context.runtime.previous_model_turn)
        self.assertNotIn("_model_turn", str(self.memory.repo.get_conversation_with_figures("s", session_id="session")))


if __name__ == "__main__":
    unittest.main()
