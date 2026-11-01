"""Recovery keeps the publication budget and does not repeat completed teaching actions."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from agents.agent_loop import LocalAgentLoop
from agents.q3_tools import AskUserTool
from agents.tool_protocol import BaseTool, ToolDefinition, ToolRegistry, ToolResult
from tests.test_q3_agent_loop import ScriptedLLM, final_round, tool_round, request
from tests.test_adaptive_tutoring import turn, record, SOURCE
from agents.adaptive_tutoring import TeachingStepTool
from agents.tool_protocol import Cancellation, CancelledError, ToolContext


class RecoveryTests(unittest.TestCase):
    def test_citation_decoration_does_not_change_the_registered_question(self):
        teaching = turn('考考我')
        prompt = '请设计实验，说明改变什么、测量什么。'
        self.assertTrue(record(teaching, check_prompt=prompt, check_focus='变量').success)
        self.assertTrue(teaching.gate(prompt + '[1]')[0])
        self.assertFalse(teaching.gate(prompt + '[1]答案是睡眠时长。')[0])
        self.assertFalse(teaching.gate('请设计实验，只说明改变什么。[1]')[0])
        self.assertEqual(teaching.progress.pending_question.prompt, prompt)

    def test_service_repairs_a_question_when_student_explicitly_forbids_questions(self):
        from agents.agent_loop_service import run_agent_loop_turn
        from agents.q3_navigation import LearningTarget, StubLearningNavigator
        from models.chat_request import ChatRequest
        from models.task_context import TaskContext
        from tests.test_q3_q4_integration import FakeMemory
        message = '直接解释自变量，不要问我。'
        model = ScriptedLLM([final_round('自变量是什么？由实验者操纵。'),
                             final_round('自变量是实验者主动操纵的条件。')])
        context = TaskContext(student_id='s', session_id='x', knowledge_point='自变量', message=message)
        req = ChatRequest(student_id='s', session_id='x', task_id='task', task_revision=1,
                          request_id='r', message=message)
        with patch.dict('os.environ', {'ADAPTIVE_TUTORING_ENABLED': '1'}), \
             patch('agents.tools.first_wave_runtime.bind_resources', return_value=(None, ())):
            result = run_agent_loop_turn(
                orchestrator=SimpleNamespace(llm=model, memory=FakeMemory(), quality_checker=None),
                request=req, context=context,
                navigator=StubLearningNavigator(target=LearningTarget(target_id='p', name='自变量')),
                publish_gate=lambda *_: (True, ''))
        self.assertEqual(result['answer_status'], 'answered')
        self.assertEqual(len(model.calls), 2)
        self.assertNotIn('？', result['reply'])
        self.assertFalse(context.tutoring['formal_mastery'])

    def test_replayed_teaching_receipt_still_satisfies_required_tool(self):
        teaching = turn('考考我')
        arguments = dict(strategy=teaching.strategy, summary='操纵变量',
                         check_prompt='自变量是什么？', check_focus='操纵',
                         check_expected_answer='操纵的变量')
        tool = TeachingStepTool(teaching)
        context = ToolContext('s', 'x', task_id='task')
        first = tool.run(arguments, context)
        question = teaching.progress.pending_question.model_dump()
        replay = tool.run(arguments, context)
        self.assertTrue(first.success and replay.success)
        self.assertEqual(replay.metadata, first.metadata)
        self.assertEqual(len(teaching.step_receipts), 1)
        self.assertEqual(teaching.progress.pending_question.model_dump(), question)

    def test_cancelled_while_waiting_for_turn_lock_cannot_register_question(self):
        teaching = turn('考考我')
        before = teaching.context.model_dump()
        cancellation = Cancellation()
        class Lock:
            def __enter__(self):
                cancellation.cancel()
            def __exit__(self, *args):
                pass
        teaching.lock = Lock()
        with self.assertRaises(CancelledError):
            TeachingStepTool(teaching).run({
                'strategy': teaching.strategy, 'summary': '操纵变量',
                'check_prompt': '自变量是什么？', 'check_focus': '操纵',
                'check_expected_answer': '操纵的变量'},
                ToolContext('s', 'x', task_id='task', cancellation=cancellation))
        self.assertEqual(teaching.context.model_dump(), before)

    def test_pause_does_not_reset_publication_repair_budget(self):
        registry = ToolRegistry()
        registry.register(AskUserTool())
        llm = ScriptedLLM([final_round('first draft'), tool_round(('ask_user', {
            'questions': [{'id': 'q', 'prompt': '对象是哪个？'}]}))])
        gate = lambda text, result: (False, '教学闭环未记录：需要修订')
        first = LocalAgentLoop(llm).run(request(llm, registry, publish_gate=gate))
        self.assertTrue(first.paused)
        self.assertTrue(first.state()['repair_used'])
        resumed_llm = ScriptedLLM([final_round('still invalid'), final_round('must not run')])
        resumed = LocalAgentLoop(resumed_llm).run(
            request(resumed_llm, registry, publish_gate=gate),
            resume_state=first.state(), answer='自变量')
        self.assertEqual(resumed.error, 'quality_rejected')
        self.assertEqual(len(resumed_llm.calls), 1)

    def test_missing_sources_get_one_host_retrieval_and_keep_gate(self):
        class Retrieve(BaseTool):
            definition = ToolDefinition('retrieve_course', 'read material')
            calls = []
            def run(self, arguments, context):
                self.calls.append(arguments)
                return ToolResult(content='material', sources=[{'source_id': 'real', 'text': '原文'}])
        registry = ToolRegistry()
        tool = Retrieve()
        registry.register(tool)
        llm = ScriptedLLM([final_round('unsupported'), final_round('supported [1]')])
        def gate(text, result):
            return (True, '') if result.sources else (False, '本轮没有可核验的教材来源，暂不发布正式回答。')
        repairs = []
        result = LocalAgentLoop(llm).run(request(llm, registry, publish_gate=gate,
            evidence_repair=lambda reason: repairs.append(reason) or 'read the current goal'))
        self.assertTrue(result.completed)
        self.assertEqual(len(tool.calls), 1)
        self.assertEqual(tool.calls[0]['query'], '解释这个概念')
        self.assertEqual(len(repairs), 1)
        self.assertTrue(result.state()['repair_used'])
        self.assertEqual(llm.calls[1]['tools'], [])

    def test_cancelled_during_gate_does_not_start_evidence_repair(self):
        class Read(BaseTool):
            definition = ToolDefinition('retrieve_course', 'read material')
            def run(self, arguments, context):
                raise AssertionError('cancelled task must not retrieve')
        registry = ToolRegistry()
        registry.register(Read())
        cancellation = Cancellation()
        llm = ScriptedLLM([final_round('draft')])
        repairs = []
        def gate(text, result):
            cancellation.cancel()
            return False, '本轮没有可核验的教材来源，暂不发布正式回答。'
        result = LocalAgentLoop(llm).run(request(llm, registry, cancellation=cancellation,
            publish_gate=gate, evidence_repair=lambda reason: repairs.append(reason) or 'repair'))
        self.assertEqual(result.error, 'cancelled')
        self.assertEqual(repairs, [])

    def test_empty_retrieval_stops_without_publishing_or_second_model_call(self):
        class Empty(BaseTool):
            definition = ToolDefinition('retrieve_course', 'no sources')
            def run(self, arguments, context):
                return ToolResult(content='no material')
        registry = ToolRegistry()
        registry.register(Empty())
        llm = ScriptedLLM([final_round('unsupported')])
        teaching = turn('按教材解释自变量，不要出题')
        result = LocalAgentLoop(llm).run(request(llm, registry,
            publish_gate=lambda text, result: (False, '本轮没有可核验的教材来源，暂不发布正式回答。'),
            evidence_repair=teaching.repair_evidence))
        self.assertEqual(result.error, 'quality_rejected')
        self.assertFalse(result.completed)
        self.assertEqual(len(llm.calls), 1)
        self.assertIsNone(teaching.plan.publication_receipt)
        self.assertFalse(teaching.state['formal_mastery'])

    def test_local_revision_keeps_prepared_question_and_receipts(self):
        teaching = turn('考考我')
        self.assertTrue(record(teaching, strategy='guided_practice', check_prompt='自变量是什么？',
                               check_focus='操纵', check_expected_answer='实验者操纵的变量').success)
        question = teaching.progress.pending_question.model_dump()
        receipts = list(teaching.step_receipts)
        decision = teaching.plan.decision_id
        teaching.repair_evidence('missing material')
        self.assertEqual(teaching.progress.pending_question.model_dump(), question)
        self.assertEqual(teaching.step_receipts, receipts)
        self.assertEqual(teaching.plan.decision_id, decision)
        self.assertEqual(teaching.plan.status, 'prepared')
        self.assertEqual(teaching.plan.evidence_recovery, 'attempted')
        with self.assertRaises(ValueError):
            teaching.repair_evidence('again')
        teaching.commit_sources([SOURCE], answer_text='请回答：自变量是什么？')
        self.assertEqual(teaching.plan.evidence_recovery, 'recovered')
        self.assertFalse(teaching.state['formal_mastery'])

    def test_recovery_cannot_be_committed_without_material(self):
        teaching = turn('按教材解释自变量')
        teaching.repair_evidence('missing material')
        self.assertIn('missing_material_after_bounded_retry', teaching.plan.stop_conditions)
        with self.assertRaisesRegex(ValueError, 'requires_sources'):
            teaching.commit_sources([], answer_text='unsupported')
        self.assertIsNone(teaching.plan.publication_receipt)


if __name__ == '__main__':
    unittest.main()
