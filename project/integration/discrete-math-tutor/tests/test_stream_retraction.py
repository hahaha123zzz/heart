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
        self.assertEqual(next(e['outcome'] for e in budget.snapshot()['stages'] if e['stage']=='slow'), 'failed')

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


    def test_required_evidence_phase_still_allows_ask_user(self):
        from agents.q3_tools import AskUserTool, RetrieveCourseTool
        from agents.ask_user_contract import build_ask_user_payload
        registry=self.registry();registry.register(AskUserTool());registry.register(RetrieveCourseTool())
        question={'questions':[{'id':'style','prompt':'希望怎样解释？','options':[{'label':'简短'},{'label':'详细'}]}]}
        llm=ScriptedLLM([tool_round(('ask_user',question))])
        result=LocalAgentLoop(llm).run(request(llm,registry,requires_evidence=True))
        self.assertTrue(result.paused, result.error)
        self.assertEqual(llm.calls[0]['tool_choice'],'required')
        self.assertIn('ask_user',[t['function']['name'] for t in llm.calls[0]['tools']])

    def test_complete_buffered_candidate_is_not_regenerated(self):
        llm=ScriptedLLM([final_round('已完成候选')]);gate=Mock(return_value=(True,''))
        result=LocalAgentLoop(llm).run(request(llm,self.registry(),publish_gate=gate))
        self.assertTrue(result.completed)
        self.assertEqual(len(llm.calls),1)
        gate.assert_called_once()


    def test_deadline_saves_terminal_receipt_without_conversation(self):
        from unittest.mock import patch
        from tests import test_clarification_tasks as fixture
        from database.models import ConversationRow
        case=fixture.ClarificationTests();case.setUp()
        self.addCleanup(case.tearDown)
        budget=ExecutionBudget(.03)
        def execute(request,context,resolved,intercept,guard,progress):
            time.sleep(.05)
            guard()
            return {'reply':'晚到回答','answer_status':'answered'}
        with patch('llm.execution_budget.ExecutionBudget',return_value=budget):
            result=case.service.run(case.request(request_id='timeout-test'),execute)
        self.assertEqual(result['answer_status'],'active_timeout')
        self.assertEqual(case.count(ConversationRow),0)
        receipt=case.repo.replay('s','tab-a','timeout-test',case.request(request_id='timeout-test').model_dump(),case.memory.repo)
        self.assertEqual(receipt['answer_status'],'active_timeout')
        self.assertIsNone(case.repo.pending('s','tab-a'))


    def test_pause_serializes_policy_without_process_deadline(self):
        from agents.agent_loop import LoopResult
        budget=ExecutionBudget(180);token=current_budget.set(budget)
        try:state=LoopResult(paused=True).state()
        finally:current_budget.reset(token)
        self.assertEqual(state['execution_policy'],{'active_limit_seconds':180})
        self.assertNotIn('deadline',str(state))
        self.assertNotIn('started',str(state))

    def test_gate_repair_retracts_only_answer_candidate_not_tool_round(self):
        events=[];publisher=AnswerEvents(lambda e,d:events.append((e,d)))
        publisher.bind(lambda:{'task_id':'t','task_revision':1},lambda:None)
        token=current_answer.set(publisher);checks=[]
        def gate(text,result):
            checks.append(text)
            return (len(checks)>1, '回复过长（超过 260 字）' if len(checks)==1 else '')
        class EmittingLLM(ScriptedLLM):
            def chat_with_tools(self,messages,tools,**kwargs):
                result=super().chat_with_tools(messages,tools,**kwargs)
                if result.text and kwargs.get('on_delta'):
                    kwargs['on_delta'](result.text)
                return result
        llm=EmittingLLM([tool_round(('echo',{'text':'原文'})),final_round('被拒候选'),final_round('修订候选')])
        try:result=LocalAgentLoop(llm).run(request(llm,self.registry(),requires_evidence=True,publish_gate=gate))
        finally:current_answer.reset(token)
        self.assertTrue(result.completed)
        clears=[d for e,d in events if e=='answer_replace' and d['text']=='']
        self.assertEqual(len(clears),1)
        self.assertEqual(clears[0]['target_round_id'],2)
        self.assertEqual(clears[0]['reason'],'candidate_rejected')
        self.assertEqual(len(llm.calls),3)


    def test_stage_feedback_uses_existing_progress_without_answer_text(self):
        budget=ExecutionBudget(1);budget.progress=Mock();token=current_budget.set(budget)
        try:stage_call('source_selection',lambda:'原文')
        finally:current_budget.reset(token)
        budget.progress.assert_called_once_with('active-source_selection.start','核对原文位置','核对原文位置，尚未保存。')


    def test_stream_close_failure_cannot_erase_partial_marker(self):
        client,sdk,stream=sdk_fixture.AnswerStreamTests().client([sdk_fixture.chunk('片段'),RuntimeError('read failed')])
        stream.close=Mock(side_effect=RuntimeError('close failed'))
        with self.assertRaises(LLMError) as caught:
            client.chat_with_tools([],[],on_delta=lambda _:None)
        self.assertTrue(caught.exception.partial_response)
        self.assertEqual(caught.exception.partial_text,'片段')
        stream.close.assert_called_once()
        self.assertEqual(sdk.chat.completions.create.call_count,1)
