"""Unified strategy boundaries and observable execution, without real model calls."""
from copy import deepcopy
import json
import unittest
from unittest.mock import Mock, patch

from agents.adaptive_tutoring import TeachingTurn, TeachingStepTool
from agents.agent_loop import LoopResult
from agents.teaching_policy import load_library, strategy_ids
from agents.teaching_strategy import TeachingStrategyPlan, runtime_strategy
from agents.tool_protocol import Cancellation, CancelledError, ToolContext
from models.chat_request import ChatRequest
from models.task_context import TaskContext
from tests.test_adaptive_tutoring import turn, prior, record, SOURCE, assessment
from tests.test_label_consumers import labeled_turn


class UnifiedStrategyTests(unittest.TestCase):
    def test_all_thirteen_have_bounded_actions_and_exit_conditions(self):
        self.assertEqual(len(strategy_ids()),13)
        for item in load_library():
            self.assertTrue(item['moves'])
            self.assertLessEqual(len(item['moves']),5)
            self.assertIn('task_cancelled_or_stale',item['stop_conditions'])

    def test_every_strategy_is_reachable_in_a_valid_context(self):
        scenarios = ['什么是自变量','分不清自变量和因变量','我还是不懂','只给提示',
                     '带我思考','考考我','帮我复习','总结一下']
        reachable = set()
        for message in scenarios:
            reachable.update(turn(message).plan.candidates)
        for verdict in ('correct','partial','incorrect'):
            model = Mock(); model.chat_json.return_value = assessment(verdict=verdict)
            t = turn('背景音乐',prior(pending=True),model,preferences={'question_frequency':1.})
            reachable.update(t.plan.candidates)
        self.assertEqual(reachable,set(strategy_ids()))

    def test_explicit_constraints_win_over_discrimination_label(self):
        with patch.dict('os.environ',{'LABELS_POLICY':'1','LABELS_TURN':'1'}):
            t = labeled_turn('我分不清自变量和因变量，只给提示，不要给完整答案')
        self.assertTrue(set(t.plan.candidates) <= {'hint','scaffolding'})
        self.assertNotIn('show_example',[m.action for m in t.plan.moves])
        self.assertEqual(t.plan.interaction_boundary,'close')

    def test_direct_request_wins_over_difficulty_and_labels(self):
        with patch.dict('os.environ',{'LABELS_POLICY':'1'}):
            t = labeled_turn('我分不清自变量和因变量，直接解释，不要出题')
        self.assertEqual(t.plan.primary_strategy,'direct_explanation')
        self.assertNotIn('ask_check',[m.action for m in t.plan.moves])

    def test_why_does_not_require_a_two_concept_comparison(self):
        t = turn('为什么要控制无关变量')
        self.assertEqual(t.plan.primary_strategy,'direct_explanation')

    def test_repeat_is_feedback_sensitive_not_a_strategy_cycle(self):
        old=prior(last_strategy='contrast')
        a=turn('什么是自变量',old)
        b=turn('讲太快，跟不上',old)
        c=turn('分不清自变量和因变量',old)
        self.assertEqual(a.plan.primary_strategy,'direct_explanation')
        self.assertEqual(b.plan.primary_strategy,'scaffolding')
        self.assertNotIn('hint',c.plan.candidates)

    def test_review_without_testing_stays_explanation(self):
        t=turn('帮我复习，只听讲，不要出题')
        self.assertNotIn('retrieval_practice',t.plan.candidates)
        self.assertNotIn('ask_check',[m.action for m in t.plan.moves])

    def test_evaluation_is_not_a_verified_misconception(self):
        t=turn('我觉得这个实验没控制好')
        self.assertNotIn('counterexample',t.plan.candidates)
        self.assertNotIn('direct_correction',t.plan.candidates)
        self.assertFalse(t.state['formal_mastery'])

    def test_model_choice_outside_candidates_has_no_side_effects(self):
        t=turn('只给提示'); before=deepcopy(t.state)
        outcome=record(t,strategy='worked_example',strategy_id='worked_example')
        self.assertFalse(outcome.success)
        self.assertEqual(t.state,before)

    def test_candidate_model_selection_uses_existing_tool(self):
        t=turn('什么是自变量')
        self.assertTrue(record(t,strategy='worked_example',strategy_id='worked_example').success)
        self.assertEqual(t.plan.reported_strategy,'worked_example')
        self.assertEqual(t.plan.status,'prepared')
        self.assertIsNone(t.plan.publication_receipt)

    def test_publication_not_model_report_creates_receipt_and_is_idempotent(self):
        t=turn('什么是自变量')
        record(t)
        self.assertIsNone(t.plan.publication_receipt)
        t.commit_sources([SOURCE],answer_text='实验者主动操纵自变量。',tool_outputs=[{'tool':'retrieve_course','result_kind':'course'}])
        t.commit_sources([SOURCE],answer_text='实验者主动操纵自变量。')
        self.assertEqual(len(t.state['strategy_history']),1)
        self.assertEqual(t.plan.tool_receipts,[{'tool':'retrieve_course','result_kind':'course'}])
        self.assertTrue(all(m.status=='not_observed' for m in t.plan.moves))
        self.assertFalse(t.state['formal_mastery'])

    def test_textbook_requirement_is_an_observable_read_action(self):
        t=turn('按教材解释自变量')
        self.assertEqual(t.plan.moves[0].action,'read_material')
        t.commit_sources([SOURCE],answer_text='教材解释[1]')
        self.assertEqual(t.plan.moves[0].status,'published')

    def test_tool_replay_does_not_repeat_state_mutation(self):
        t=turn('什么是自变量')
        self.assertTrue(record(t).success)
        before=deepcopy(t.state)
        self.assertTrue(record(t).success)
        self.assertEqual(t.state,before)

    def test_cancelled_tool_does_not_record(self):
        t=turn('什么是自变量'); cancellation=Cancellation(); cancellation.cancel()
        with self.assertRaises(CancelledError):
            TeachingStepTool(t).run({'strategy':'explain','summary':'定义'},
                ToolContext(student_id='s',session_id='x',cancellation=cancellation))
        self.assertEqual(t.plan.status,'planned')
        self.assertFalse(t.state['strategy_history'])

    def test_feedback_is_linked_to_publication_without_causal_claims(self):
        t=turn('什么是自变量'); record(t); t.commit_sources([SOURCE],answer_text='解释变量')
        request=ChatRequest(student_id='s',session_id='x',request_id='next',message='还是不懂')
        context=TaskContext(student_id='s',session_id='x',knowledge_point='自变量',message=request.message,tutoring=t.state)
        followup=TeachingTurn(context,request,Mock(),validate_sources=lambda x:x)
        feedback=followup.state['strategy_history'][-1]['feedback'][-1]
        self.assertTrue(feedback['difficulty_reported'])
        self.assertFalse(feedback['causal_effect'])
        self.assertEqual(feedback['verification'],'self_report')

    def test_resume_preserves_identity_pending_and_prepared_move(self):
        request=ChatRequest(student_id='s',session_id='x',request_id='r',task_id='task',task_revision=1,message='考考我')
        context=TaskContext(student_id='s',session_id='x',knowledge_point='自变量',message=request.message)
        first=TeachingTurn(context,request,Mock(),validate_sources=lambda x:x)
        self.assertTrue(record(first,check_prompt='实验者操纵什么？',check_focus='变量').success)
        saved=deepcopy(first.state)
        req=request.model_copy(update={'request_id':'resume','task_revision':2,'message':'考考我\n补充说明：开始'})
        ctx=context.model_copy(deep=True);ctx.tutoring=saved
        model=Mock()
        resumed=TeachingTurn(ctx,req,model,validate_sources=lambda x:x,resume=True)
        self.assertEqual(resumed.plan.decision_id,first.plan.decision_id)
        self.assertEqual(resumed.progress.pending_question.question_id,first.progress.pending_question.question_id)
        self.assertTrue(resumed.new_question)
        self.assertTrue(resumed.recorded)
        self.assertEqual(resumed.step_receipts,first.step_receipts)
        model.chat_json.assert_not_called()

    def test_cross_task_resume_rejected(self):
        first=turn('什么是自变量');record(first)
        request=first.request.model_copy(update={'task_id':'other-task'})
        with self.assertRaisesRegex(ValueError,'scope_changed'):
            TeachingTurn(first.context,request,Mock(),resume=True)

    def test_public_plan_has_no_private_answers_or_student_identity(self):
        t=turn('只给提示',prior(pending=True))
        public=json.dumps(t.public(),ensure_ascii=False)
        self.assertNotIn('PRIVATE-',public)
        self.assertNotIn('student_id',t.public()['strategy_plan'])
        self.assertNotIn('session_id',t.public()['strategy_plan'])

    def test_loop_resume_state_preserves_successful_tool_receipts(self):
        result=LoopResult(tool_outputs=[{'tool':'teaching_step','result_kind':'teaching_step'}])
        self.assertEqual(result.state()['tool_outputs'],result.tool_outputs)

    def test_loop_service_restores_paused_teaching_not_only_messages(self):
        from types import SimpleNamespace
        from agents.agent_loop_service import run_agent_loop_turn
        from agents.q3_navigation import LearningTarget, StubLearningNavigator
        from llm.client import ChatToolResult
        from tests.test_q3_q4_integration import ScriptedLLM, FakeMemory, tool_round
        model=ScriptedLLM([
            tool_round('teaching_step',{'strategy':'explain','summary':'解释变量'}),
            tool_round('ask_user',{'questions':[{'id':'example','prompt':'下一步用哪种例子？','options':[{'label':'生活例子'},{'label':'研究例子'}]}]}),
            ChatToolResult(text='研究者主动改变条件，这个条件就是自变量。',finish_reason='stop')])
        model.rounds[1].tool_calls[0].id='ask-example'
        request=ChatRequest(student_id='s',session_id='x',task_id='task',task_revision=1,request_id='r',message='什么是自变量')
        context=TaskContext(student_id='s',session_id='x',knowledge_point='自变量',message=request.message)
        host=SimpleNamespace(llm=model,memory=FakeMemory(),quality_checker=None)
        navigator=StubLearningNavigator(target=LearningTarget(target_id='p',name='自变量'))
        with patch.dict('os.environ',{'ADAPTIVE_TUTORING_ENABLED':'1'}), \
             patch('agents.tools.first_wave_runtime.bind_resources',return_value=(None,())):
            paused=run_agent_loop_turn(orchestrator=host,request=request,context=context,
                navigator=navigator,publish_gate=lambda *_:(True,''))
            self.assertTrue(paused.get('loop_paused'),paused)
            decision=context.tutoring['strategy_plan']['decision_id']
            previous={'context':context.model_dump() | {'loop_state':paused['loop_state']},'_resume_answer':'生活例子'}
            # TaskService reconstructs context from committed turns before the loop
            # restores the server-owned paused snapshot.
            fresh=context.model_copy(deep=True);fresh.tutoring={}
            resumed=run_agent_loop_turn(orchestrator=host,
                request=request.model_copy(update={'request_id':'resume','task_revision':2}),context=fresh,
                navigator=navigator,previous=previous,publish_gate=lambda *_:(True,''))
        self.assertEqual(resumed['answer_status'],'answered')
        self.assertEqual(resumed['teaching']['strategy_plan']['decision_id'],decision)
        self.assertEqual(resumed['teaching']['strategy_plan']['reported_strategy'],'direct_explanation')
        self.assertEqual(len(fresh.tutoring['strategy_step_receipts']),1)
        self.assertEqual(len(fresh.tutoring['strategy_history']),1)

    def test_selection_constraint_narrows_the_same_plan_before_generation(self):
        t=turn('解释一下')
        identity=t.plan.decision_id
        t.apply_strategy_constraints(['hint_only','no_full_answer','no_questions'])
        self.assertEqual(t.plan.decision_id,identity)
        self.assertTrue(set(t.plan.candidates) <= {'hint','scaffolding'})
        self.assertFalse(t.plan.allow_check)
        self.assertTrue(t.limit_disclosure)
        self.assertFalse(record(t,strategy='worked_example',strategy_id='worked_example').success)

    def test_summary_update_preserves_already_registered_check_move(self):
        t=turn('考考我')
        self.assertTrue(record(t,check_prompt='操纵什么？',check_focus='变量').success)
        self.assertTrue(record(t,summary='补充已登记动作的摘要').success)
        self.assertTrue(any(m.action == 'ask_check' for m in t.plan.moves))
        self.assertEqual(t.plan.interaction_boundary,'wait_for_student')

    def test_prepared_plan_cannot_reselect_a_strategy_removed_by_selection_constraints(self):
        t=turn('我还是不懂')
        self.assertTrue(record(t,strategy='break_down',strategy_id='scaffolding').success)
        identity=t.plan.decision_id
        t.apply_strategy_constraints(['hint_only','no_full_answer','no_questions'])
        self.assertEqual(t.plan.decision_id,identity)
        self.assertEqual(t.plan.status,'prepared')
        self.assertTrue(set(t.plan.candidates) <= {'hint','scaffolding'})
        self.assertIn(t.plan.fallback,t.plan.candidates)
        self.assertFalse(record(t,strategy='worked_example',strategy_id='worked_example').success)


if __name__=='__main__': unittest.main()
