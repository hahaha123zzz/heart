"""Q3 本地循环、工具协议、ask_user 与恢复的离线验证。"""
import json
import time
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

from agents.agent_loop import LocalAgentLoop, LoopRequest
from agents.ask_user_contract import build_ask_user_payload, format_user_reply, substitute_answer
from agents.q3_navigation import LearningTarget, SourceRef, StubLearningNavigator
from agents.q3_tools import AskUserTool, RetrieveCourseTool
from agents.tool_dispatch import dispatch_tool_calls
from agents.tool_protocol import (
    BaseTool, Cancellation, ToolContext, ToolDefinition, ToolParameter,
    ToolRegistry, ToolResult,
)
from llm.client import ChatToolCall, ChatToolResult, LLMClient, LLMError


class EchoTool(BaseTool):
    definition = ToolDefinition("echo", "回显参数",
        (ToolParameter("text", "string", "要回显的文字"),))

    def run(self, arguments, context):
        return ToolResult(content="echo:" + arguments["text"],
                          sources=[{"source_id": "s1", "text": arguments["text"]}],
                          metadata={"ok": True})


class FailTool(BaseTool):
    definition = ToolDefinition("fail", "总是失败")

    def run(self, arguments, context):
        raise RuntimeError("boom")


class ScriptedLLM:
    def __init__(self, rounds):
        self.rounds = list(rounds)
        self.calls = []

    def chat_with_tools(self, messages, tools, **kwargs):
        self.calls.append({"messages": deepcopy(messages), "tools": deepcopy(tools), **kwargs})
        if not self.rounds:
            raise LLMError("script exhausted")
        item = self.rounds.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def tool_round(*calls, text=""):
    return ChatToolResult(text=text, finish_reason="tool_calls", tool_calls=[
        ChatToolCall(id=f"call_{index}", name=name, arguments=args,
                     raw_arguments=json.dumps(args, ensure_ascii=False))
        for index, (name, args) in enumerate(calls)
    ])


def final_round(text):
    return ChatToolResult(text=text, finish_reason="stop")


def request(llm, registry, *, message="解释这个概念", target=None, **kwargs):
    return LoopRequest(
        student_id="s", session_id="session", task_id="task", request_id="request",
        message=message, system_prompt="你是助教。", tools=registry,
        target=target, **kwargs,
    )


class ToolProtocolTests(unittest.TestCase):
    def test_registry_schemas_do_not_include_unmounted_tools(self):
        registry = ToolRegistry(); registry.register(EchoTool())
        schemas = registry.schemas()
        self.assertEqual(schemas[0]["function"]["name"], "echo")
        self.assertIsNone(registry.get("missing"))

    def test_dispatch_dedupes_unknown_and_keeps_pairing(self):
        registry = ToolRegistry(); registry.register(EchoTool())
        context = ToolContext("s", "session", cancellation=Cancellation())
        outcome = dispatch_tool_calls(tool_calls=[
            {"id": "a", "name": "echo", "arguments": {"text": "hi"}},
            {"id": "b", "name": "echo", "arguments": {"text": "hi"}},
            {"id": "c", "name": "missing", "arguments": {}},
        ], registry=registry, context=context)
        self.assertEqual([m["tool_call_id"] for m in outcome.tool_messages], ["a", "b", "c"])
        self.assertIn("echo:hi", outcome.tool_messages[0]["content"])
        self.assertIn("重复", outcome.tool_messages[1]["content"])
        self.assertIn("不在本轮工具列表", outcome.tool_messages[2]["content"])

    def test_dispatch_returns_tool_error_without_raising(self):
        registry = ToolRegistry(); registry.register(FailTool())
        outcome = dispatch_tool_calls(tool_calls=[
            {"id": "a", "name": "fail", "arguments": {}}],
            registry=registry, context=ToolContext("s", "session"))
        self.assertFalse(outcome.results[0].success)
        self.assertIn("boom", outcome.tool_messages[0]["content"])

    def test_dispatch_timeout_is_bounded(self):
        class SlowTool(BaseTool):
            definition = ToolDefinition("slow", "慢工具")

            def run(self, arguments, context):
                time.sleep(0.3)
                return ToolResult(content="late")

        registry = ToolRegistry(); registry.register(SlowTool())
        started = time.monotonic()
        outcome = dispatch_tool_calls(tool_calls=[
            {"id": "a", "name": "slow", "arguments": {}}],
            registry=registry, context=ToolContext("s", "session"), timeout_seconds=0.05)
        self.assertLess(time.monotonic() - started, 0.2)
        self.assertFalse(outcome.results[0].success)
        self.assertIn("超时", outcome.tool_messages[0]["content"])

    def test_dispatch_pause_signal(self):
        registry = ToolRegistry(); registry.register(AskUserTool())
        outcome = dispatch_tool_calls(tool_calls=[
            {"id": "ask", "name": "ask_user", "arguments": {
                "questions": [{"id": "q1", "prompt": "你指哪种设计？",
                               "options": [{"label": "被试间"}, {"label": "被试内"}]}]}}],
            registry=registry, context=ToolContext("s", "session"))
        self.assertTrue(outcome.pause)
        self.assertEqual(outcome.pause_tool_call_id, "ask")
        self.assertEqual(outcome.pause_payload["ask_user"]["questions"][0]["id"], "q1")


class AskUserContractTests(unittest.TestCase):
    def test_v2_and_legacy_payloads_normalise(self):
        payload, error = build_ask_user_payload(questions=[
            {"id": "q1", "prompt": "哪一种？", "options": ["A", "B"]}])
        self.assertIsNone(error)
        self.assertEqual(payload.questions[0].options[0].label, "A")
        legacy, error = build_ask_user_payload(question="哪一种？", options=["A"])
        self.assertIsNone(error)
        self.assertEqual(legacy.questions[0].prompt, "哪一种？")
        self.assertIsNotNone(build_ask_user_payload(questions=[])[1])

    def test_answer_substitution_hits_the_paused_call_only(self):
        messages = [{"role": "tool", "tool_call_id": "ask", "content": "waiting"}]
        directive = format_user_reply({"questions": [{"id": "q1", "prompt": "哪一种？"}]},
                                      "被试内设计")
        self.assertIn("被试内设计", directive)
        self.assertTrue(substitute_answer(messages, "ask", directive))
        self.assertEqual(messages[0]["content"], directive)
        self.assertFalse(substitute_answer(messages, "other", "x"))


class LLMToolProtocolTests(unittest.TestCase):
    def test_chat_with_tools_parses_calls_and_usage(self):
        client = LLMClient(api_key="test", mock=False)
        raw_call = SimpleNamespace(id="call_1", function=SimpleNamespace(
            name="echo", arguments='{"text":"你好"}'))
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="", tool_calls=[raw_call]),
                                     finish_reason="tool_calls")],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=4, total_tokens=14),
        )
        fake = Mock(); fake.chat.completions.create.return_value = response
        client._client_lazy = Mock(return_value=fake)
        result = client.chat_with_tools([{"role": "user", "content": "hi"}],
                                        [{"type": "function", "function": {"name": "echo"}}])
        self.assertEqual(result.tool_calls[0].name, "echo")
        self.assertEqual(result.tool_calls[0].arguments, {"text": "你好"})
        self.assertEqual(result.usage["total_tokens"], 14)
        args = fake.chat.completions.create.call_args.kwargs
        self.assertEqual(args["tool_choice"], "auto")


class AgentLoopTests(unittest.TestCase):
    def registry(self):
        registry = ToolRegistry(); registry.register(EchoTool()); registry.register(AskUserTool())
        return registry

    def test_runs_tool_then_final_answer(self):
        llm = ScriptedLLM([tool_round(("echo", {"text": "hi"})), final_round("最终回答")])
        result = LocalAgentLoop(llm).run(request(llm, self.registry()))
        self.assertTrue(result.completed)
        self.assertEqual(result.final_text, "最终回答")
        self.assertEqual(result.tool_steps, 1)
        self.assertEqual(result.sources[0]["source_id"], "s1")
        roles = [message["role"] for message in result.messages]
        self.assertEqual(roles, ["system", "user", "assistant", "tool", "assistant"])

    def test_budget_forces_a_tool_free_finish(self):
        llm = ScriptedLLM([tool_round(("echo", {"text": "x"})) for _ in range(3)] +
                          [final_round("收尾回答")])
        result = LocalAgentLoop(llm).run(request(
            llm, self.registry(), max_exploration_rounds=2, max_settlement_rounds=1))
        self.assertTrue(result.completed)
        self.assertEqual(result.final_text, "收尾回答")
        self.assertLessEqual(len(llm.calls), 5)
        self.assertEqual(llm.calls[-1]["tools"], [])

    def test_ask_user_pauses_and_resumes_same_task(self):
        llm = ScriptedLLM([
            tool_round(("ask_user", {"questions": [{"id": "q1", "prompt": "你指哪一种？"}]})),
            final_round("按被试内设计解释。"),
        ])
        loop = LocalAgentLoop(llm)
        paused = loop.run(request(llm, self.registry()))
        self.assertTrue(paused.paused)
        self.assertFalse(paused.completed)
        self.assertEqual(paused.pending_question["questions"][0]["id"], "q1")
        resumed = loop.run(request(llm, self.registry()), resume_state=paused.state(),
                           answer="被试内设计")
        self.assertTrue(resumed.completed)
        self.assertEqual(resumed.final_text, "按被试内设计解释。")
        tool_message = next(message for message in llm.calls[1]["messages"]
                            if message.get("role") == "tool")
        self.assertIn("被试内设计", tool_message["content"])
        self.assertIn("继续", tool_message["content"])

    def test_cancellation_stops_before_next_round(self):
        cancel = Cancellation()
        llm = ScriptedLLM([tool_round(("echo", {"text": "hi"})), final_round("不应执行")])
        registry = self.registry()

        class CancelAfterEcho(EchoTool):
            def run(self, arguments, context):
                result = super().run(arguments, context)
                cancel.cancel()
                return result

        registry = ToolRegistry(); registry.register(CancelAfterEcho())
        result = LocalAgentLoop(llm).run(request(llm, registry, cancellation=cancel))
        self.assertFalse(result.completed)
        self.assertEqual(result.error, "cancelled")
        self.assertEqual(len(llm.calls), 1)

    def test_length_gate_gets_one_bounded_repair(self):
        calls = []
        def gate(text, state):
            calls.append(text)
            return (len(calls) > 1, "" if len(calls) > 1 else "回复过长（超过 260 字）")
        llm = ScriptedLLM([final_round("很长的草稿" * 80), final_round("压缩后的回答")])
        result = LocalAgentLoop(llm).run(request(llm, self.registry(), publish_gate=gate))
        self.assertTrue(result.completed)
        self.assertEqual(result.final_text, "压缩后的回答")
        self.assertEqual(len(calls), 2)
        self.assertEqual(llm.calls[1]["tools"], [])

    def test_publish_gate_rejects_without_publishing(self):
        llm = ScriptedLLM([final_round("未经核验的回答")])
        result = LocalAgentLoop(llm).run(request(
            llm, self.registry(), publish_gate=lambda text, state: (False, "未通过引用核验")))
        self.assertFalse(result.completed)
        self.assertEqual(result.error, "quality_rejected")
        self.assertNotIn("未经核验的回答", result.final_text)

    def test_first_round_model_failure_is_reported(self):
        llm = ScriptedLLM([LLMError("offline")])
        result = LocalAgentLoop(llm).run(request(llm, self.registry()))
        self.assertFalse(result.completed)
        self.assertIn("model_unavailable", result.error)

    def test_failure_after_tool_uses_bounded_forced_finish(self):
        llm = ScriptedLLM([tool_round(("echo", {"text": "hi"})), LLMError("offline"),
                           final_round("基于已有材料的回答")])
        result = LocalAgentLoop(llm).run(request(llm, self.registry()))
        self.assertTrue(result.completed)
        self.assertEqual(result.final_text, "基于已有材料的回答")


class QualityGateOverrideTests(unittest.TestCase):
    def test_loop_can_request_a_bounded_500_char_check(self):
        from agents.quality_checker import QualityChecker
        from agents.teaching_planner import TeachingPlan
        from models.student_state import StudentState

        llm = Mock()
        llm.chat_json.return_value = {"passed": True, "issues": []}
        plan = TeachingPlan(goal="解释", strategy="worked_example",
                            action="explain", difficulty="medium")
        QualityChecker(llm).check("说明。" * 120, StudentState(), plan, "请解释",
                                  context={"reply_maximum_override": 500},
                                  textbook_excerpts="[1] 教材原文")
        prompt = llm.chat_json.call_args.args[0][1]["content"]
        self.assertIn("可到500字", prompt)


class NavigationBoundaryTests(unittest.TestCase):
    def test_next_topic_without_a_course_path_asks_for_target(self):
        target = LearningTarget("kp-1", "自变量")
        navigator = StubLearningNavigator(target=target)
        decision = navigator.resolve(message="继续下一知识点", student_id="s",
                                     session_id="x", current_target=target, context=None)
        self.assertEqual(decision.action, "clarify")
        self.assertEqual(decision.missing, ("target",))

    def test_retrieval_uses_resolved_target_not_raw_navigation_sentence(self):
        target = LearningTarget("kp-1", "自变量", chapter_id=2, section_id=2)
        navigator = StubLearningNavigator(target=target, sources=[
            SourceRef("s1", "chapter-02", "自变量是研究者操纵的变量。", version="v1",
                      chapter_id=2, section_id=2, page=2)])
        decision = navigator.resolve(message="解释这个概念", student_id="s", session_id="x",
                                     current_target=target, context=None)
        self.assertEqual(decision.action, "teach")
        registry = ToolRegistry(); registry.register(RetrieveCourseTool())
        context = ToolContext("s", "session", navigation=navigator,
                              state={"learning_target": target})
        result = RetrieveCourseTool().run({"query": "下一知识点"}, context)
        self.assertTrue(result.success)
        self.assertIn("自变量是研究者操纵的变量", result.content)
        self.assertTrue(result.sources[0]["stub"])
        self.assertEqual(navigator.calls[-1], ("search", "kp-1"))


if __name__ == "__main__":
    unittest.main()
