"""隔离流式角色、部分中断及共享活动预算回归。"""
import time
import unittest
from unittest.mock import Mock
from llm.answer_events import AnswerEvents, current_answer, answer_kwargs
from llm.client import LLMError
from llm.execution_budget import ExecutionBudget, current_budget, BudgetExceeded, stage_call
from agents.agent_loop import LocalAgentLoop
from agents.tool_protocol import ToolRegistry
from tests.test_q3_agent_loop import EchoTool, ScriptedLLM, request, tool_round, final_round
from tests import test_answer_stream as sdk_fixture


class RetractionTests(unittest.TestCase):
    def registry(self):
        registry = ToolRegistry()
        registry.register(EchoTool())
        return registry

    def test_partial_answer_after_tool_never_generates_third_round(self):
        llm = ScriptedLLM([tool_round(('echo', {'text': '原文'})),
            LLMError('连接中断', partial_text='未完成片段', usage={'completion_tokens': 4}),
            final_round('不应执行')])
        result = LocalAgentLoop(llm).run(request(llm, self.registry(), requires_evidence=True))
        self.assertEqual(len(llm.calls), 2)
        self.assertFalse(result.completed)
        self.assertEqual(result.error, 'answer_interrupted')
        self.assertEqual(result.unpublished_draft, '未完成片段')
        self.assertNotIn('未完成片段', str(result.messages))
        self.assertEqual(result.usage['completion_tokens'], 4)
        self.assertEqual(llm.calls[1]['tools'], [])

    def test_length_is_not_transport_recovery(self):
        llm = ScriptedLLM([LLMError('长度不足', partial_text='片段', finish_reason='length')])
        result = LocalAgentLoop(llm).run(request(llm, ToolRegistry()))
        self.assertEqual(result.error, 'incomplete_answer')
        self.assertEqual(len(llm.calls), 1)

    def test_no_output_after_valid_evidence_recovers_only_once(self):
        llm = ScriptedLLM([tool_round(('echo', {'text': '原文'})), LLMError('无输出'), LLMError('仍无输出')])
        result = LocalAgentLoop(llm).run(request(llm, self.registry(), requires_evidence=True))
        self.assertEqual(len(llm.calls), 3)
        self.assertFalse(result.completed)

    def test_progress_text_never_emitted_and_begin_does_not_clear(self):
        events=[]
        publisher=AnswerEvents(lambda e,d: events.append((e,d)))
        publisher.bind(lambda: {'task_id':'t','task_revision':1}, lambda:None)
        token=current_answer.set(publisher)
        try:
            answer_kwargs('progress')['on_delta']('待查询的猜测')
            answer_kwargs('answer')['on_delta']('已有依据的候选')
            answer_kwargs('progress')['on_delta']('补查说明')
        finally:
            current_answer.reset(token)
        self.assertEqual([d['text'] for e,d in events if e=='answer_delta'], ['已有依据的候选'])
        self.assertFalse(any(e=='answer_replace' for e,d in events))

    def test_sdk_exception_preserves_partial_and_closes(self):
        client,sdk,stream=sdk_fixture.AnswerStreamTests().client([sdk_fixture.chunk('片段'), RuntimeError('read failed')])
        with self.assertRaises(LLMError) as caught:
            client.chat_with_tools([], [], on_delta=lambda text: None)
        self.assertEqual(caught.exception.partial_text, '片段')
        self.assertTrue(stream.closed)
        self.assertEqual(sdk.chat.completions.create.call_count, 1)

    def test_total_budget_bounds_nested_stages_and_late_output(self):
        budget=ExecutionBudget(.04)
        token=current_budget.set(budget)
        emitted=[]
        def slow():
            time.sleep(.08)
            stage_call('late', lambda:emitted.append('late'))
        try:
            with self.assertRaises(BudgetExceeded):
                stage_call('slow', slow)
            with self.assertRaises(BudgetExceeded):
                stage_call('next', lambda: emitted.append('next'))
            time.sleep(.09)
        finally:
            current_budget.reset(token)
        self.assertEqual(emitted, [])
        self.assertEqual(budget.snapshot()['stages'][0]['outcome'], 'failed')

    def test_budget_propagates_to_tool_threads(self):
        from agents.tool_dispatch import dispatch_tool_calls
        from agents.tool_protocol import ToolContext, BaseTool, ToolDefinition, ToolResult
        seen=[]
        class Tool(BaseTool):
            definition=ToolDefinition('budget', '查看活动预算')
            def run(self, arguments, context):
                seen.append(current_budget.get())
                return ToolResult(content='ok')
        registry=ToolRegistry();registry.register(Tool())
        budget=ExecutionBudget(1);token=current_budget.set(budget)
        try:
            dispatch_tool_calls(tool_calls=[{'id':'t','name':'budget','arguments':{}}],
                registry=registry, context=ToolContext('s','tab'))
        finally:
            current_budget.reset(token)
        self.assertEqual(seen, [budget])
