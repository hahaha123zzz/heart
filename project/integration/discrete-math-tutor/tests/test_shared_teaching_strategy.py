"""Shared policy consumption at legacy, selection, exercise and native boundaries."""
from copy import deepcopy
import json
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

from agents.task_execution import TaskExecution
from agents.teaching_strategy import decide_for_context,publish_external_strategy,strategy_prompt
from agents.quality_checker import QualityResult
from models.task_context import TaskContext
from models.student_state import StudentState
from tests.test_adaptive_tutoring import turn


def context(message,**values):
    return TaskContext(student_id='shared-student',session_id='shared-session',request_id='shared-request',
        task_id='shared-task',task_revision=3,knowledge_point='自变量',message=message,**values)


class SharedStrategyPolicyTests(unittest.TestCase):
    def test_context_adapter_matches_turn_for_explicit_requests(self):
        for message in ('直接解释自变量，不要出题','只给提示','我还是不懂','自变量和因变量有什么区别'):
            with self.subTest(message=message):
                shared=decide_for_context(context(message),TaskExecution())
                host=turn(message)
                self.assertEqual(shared.primary_strategy,host.plan.primary_strategy)
                self.assertEqual(shared.candidates,host.plan.candidates)

    def test_claimed_task_identity_is_bound_and_hidden_from_intent_payload(self):
        ctx=context('直接解释')
        plan=decide_for_context(ctx,TaskExecution())
        self.assertEqual((plan.task_id,plan.task_revision),('shared-task',3))
        self.assertNotIn('task_id',ctx.prompt_payload())
        self.assertNotIn('task_revision',ctx.prompt_payload())

    def test_explicit_no_full_answer_survives_legacy_direct_mode(self):
        from agents.task_execution import build_execution
        message='直接告诉我答案，但不要给我完整答案'
        ctx=context(message)
        execution=build_execution(message,SimpleNamespace(learning_intents=[],target_refs=[],answer_constraints=[]),ctx)
        self.assertTrue(execution.hint_only)
        plan=decide_for_context(ctx,execution)
        self.assertEqual(plan.primary_strategy,'hint')
        self.assertFalse(plan.allow_check)

    def test_requesting_a_quiz_without_answers_still_allows_the_question(self):
        ctx=context('考考我，不要替我作答')
        plan=decide_for_context(ctx,TaskExecution(teaching_mode='practice',answer_constraints=['no_full_answer']))
        self.assertEqual(plan.primary_strategy,'retrieval_practice')
        self.assertTrue(plan.allow_check)

    def test_verdict_only_overrides_high_question_frequency(self):
        ctx=context('只判断对错',preferences={'question_frequency':1.})
        plan=decide_for_context(ctx,TaskExecution(answer_constraints=['verdict_only']))
        self.assertFalse(plan.allow_check)
        self.assertNotEqual(plan.interaction_boundary,'wait_for_student')

    def test_external_publication_is_idempotent_and_never_marks_semantic_moves_complete(self):
        ctx=context('请解释自变量');before=deepcopy(ctx.tutoring)
        plan=decide_for_context(ctx,TaskExecution())
        self.assertEqual(ctx.tutoring,before)
        self.assertIsNone(plan.publication_receipt)
        result=publish_external_strategy(ctx,plan,'研究者主动操纵自变量。')
        publish_external_strategy(ctx,plan,'研究者主动操纵自变量。')
        self.assertEqual(len(ctx.tutoring['strategy_history']),1)
        self.assertNotIn('student_id',result)
        self.assertNotIn('session_id',result)
        self.assertTrue(all(m.status=='not_observed' for m in plan.moves))
        self.assertNotIn('formal_mastery',ctx.tutoring)

    def test_other_target_strategy_does_not_change_current_difficulty_choice(self):
        ctx=context('我还是不懂')
        ctx.tutoring={'strategy_plan':{'primary_strategy':'worked_example','target_ref':'other-target'}}
        plan=decide_for_context(ctx,TaskExecution())
        self.assertEqual(plan.primary_strategy,'worked_example')
        self.assertFalse(any(r.startswith('previous_published') for r in plan.decision_summary))

    def test_feedback_is_linked_only_to_same_target_publication(self):
        ctx=context('我还是不懂')
        ctx.tutoring={'strategy_history':[{'decision_id':'a','target_ref':'自变量','feedback':[]},
            {'decision_id':'b','target_ref':'other-target','feedback':[]}]}
        plan=decide_for_context(ctx,TaskExecution())
        publish_external_strategy(ctx,plan,'换一个具体的例子。')
        self.assertTrue(ctx.tutoring['strategy_history'][0]['feedback'])
        self.assertFalse(ctx.tutoring['strategy_history'][1]['feedback'])
        self.assertFalse(ctx.tutoring['strategy_history'][0]['feedback'][0]['causal_effect'])

    def test_legacy_prompt_does_not_request_a_tool_that_is_not_installed(self):
        plan=decide_for_context(context('只给提示'),TaskExecution())
        self.assertNotIn('teaching_step',strategy_prompt(plan,selector_tool=False))

    def test_legacy_chat_uses_one_policy_and_keeps_user_no_question_boundary(self):
        from tests.test_answer_flow import AnswerFlowTests
        from models.task_understanding import TaskUnderstanding
        fixture=AnswerFlowTests()
        tutor=fixture.tutor()
        tutor.conversation_router.route.return_value=TaskUnderstanding(student_move='statement',
            confidence=1.,learning_intents=['explain'])
        with patch.dict('os.environ',{'ADAPTIVE_TUTORING_ENABLED':'1'}):
            result=fixture.run_turn(tutor,'我还是不懂，直接解释，不要出题。')
        self.assertEqual(result['answer_status'],'answered')
        plan=result['teaching_strategy_plan']
        self.assertEqual(plan['primary_strategy'],'direct_explanation')
        self.assertEqual(result['teaching_plan']['strategy'],plan['primary_strategy'])
        self.assertIsNotNone(plan['publication_receipt'])
        tutor.teaching_planner.plan.assert_not_called()
        tutor.strategy_router.select.assert_not_called()
        tutor.question_designer.design.assert_not_called()
        self.assertIn('统一教学决策',tutor.response_generator.generate.call_args.args[5])

    def test_native_snapshot_uses_same_policy_and_is_scoped_to_task_revision(self):
        from integrations.deeptutor.teaching_prompt_adapter import teaching_snapshot,teaching_prompt_scope,_style
        from integrations.deeptutor.client import BackendUnavailable
        identity=SimpleNamespace(student_id='shared-student',session_id='shared-session',
            request_id='shared-request',task_id='shared-task',task_revision=3)
        with patch.dict('os.environ',{'ADAPTIVE_TUTORING_ENABLED':'1'}):
            snapshot=teaching_snapshot('只给提示',identity=identity)
        self.assertEqual(snapshot['strategy_plan']['primary_strategy'],'hint')
        entry=vars(identity)|{'teaching_style':json.dumps(snapshot,ensure_ascii=False)}
        with patch('integrations.deeptutor.teaching_prompt_adapter.install_teaching_prompt_adapter'):
            with teaching_prompt_scope(entry):
                self.assertEqual(_style.get()['strategy_plan'].task_revision,3)
            self.assertIsNone(_style.get())
            with self.assertRaises(BackendUnavailable):
                with teaching_prompt_scope(entry|{'task_revision':4}): pass


class LegacySelectionPolicyTests(unittest.TestCase):
    def setUp(self):
        from tests.test_task_resource_execution import TaskResourceExecutionTests
        self.fixture=TaskResourceExecutionTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)

    def test_hint_selection_consumes_policy_before_generation_and_receipts_after_quality(self):
        tutor,ctx,resolved,selection=self.fixture.pdf_tutor(QualityResult(passed=True))
        ctx.task_id='selection-task';ctx.task_revision=2
        with patch.dict('os.environ',{'ADAPTIVE_TUTORING_ENABLED':'1'}), \
             patch('knowledge.grounded_citations.settings',return_value=None):
            result=self.fixture.pdf_run(tutor,ctx,resolved,selection)
        self.assertEqual(result['teaching_strategy_plan']['primary_strategy'],'hint')
        self.assertIn('统一教学决策',tutor.llm.chat.call_args.args[0][0]['content'])
        self.assertEqual(tutor.quality_checker.check.call_args.args[2].strategy,'hint')
        self.assertTrue(result['teaching_strategy_plan']['publication_receipt'])

    def test_validated_selection_request_does_not_repeat_input_classification(self):
        from agents.input_understanding.service import understand
        from models.chat_request import ChatRequest
        tutor,ctx,resolved,selection=self.fixture.pdf_tutor(QualityResult(passed=True))
        ctx.input_mode='active';ctx.current_object_ids=['selection-current']
        request=ChatRequest(student_id=ctx.student_id,session_id=ctx.session_id,message=ctx.message)
        ctx.input_understanding=understand(ctx,request)
        # The actual selection HTTP request supplies this already-resolved object binding.
        value=ctx.input_understanding.model_dump()
        value['tasks'][0]['target_ref']=value['references'][0]['ref_id']
        ctx.input_understanding=type(ctx.input_understanding).model_validate(value)
        with patch.dict('os.environ',{'ADAPTIVE_TUTORING_ENABLED':'1'}), \
             patch('knowledge.grounded_citations.settings',return_value=None):
            result=self.fixture.pdf_run(tutor,ctx,resolved,selection)
        self.assertEqual(result['answer_status'],'answered')
        tutor.conversation_router.route.assert_not_called()

    def test_failed_quality_has_no_strategy_publication(self):
        from llm.client import LLMError
        tutor,ctx,resolved,selection=self.fixture.pdf_tutor(QualityResult(passed=False,issues=['answer disclosed']))
        with patch.dict('os.environ',{'ADAPTIVE_TUTORING_ENABLED':'1'}), \
             patch('knowledge.grounded_citations.settings',return_value=None),self.assertRaises(LLMError):
            self.fixture.pdf_run(tutor,ctx,resolved,selection)
        self.assertNotIn('strategy_plan',ctx.tutoring)
        self.assertNotIn('strategy_history',ctx.tutoring)


class ExercisePolicyTests(unittest.TestCase):
    def setup_inputs(self):
        import practice_api as api
        from tests.test_ai_practice_test import load_catalog,FIXTURE,COURSE
        q=load_catalog(FIXTURE,COURSE)['questions'][0]
        tutor=SimpleNamespace(llm=Mock(),quality_checker=Mock(),memory=Mock())
        tutor.llm.chat.return_value='先定位研究者主动操纵的因素。'
        tutor.quality_checker.check.return_value=QualityResult(passed=True)
        tutor.memory.get_state.return_value=StudentState()
        return api,q,tutor

    def test_exercise_hint_uses_shared_plan_and_never_includes_other_part_answers(self):
        api,q,tutor=self.setup_inputs();ctx=context('只给提示')
        with patch.dict('sys.modules',{'main':SimpleNamespace(orchestrator=tutor)}), \
             patch.dict('os.environ',{'ADAPTIVE_TUTORING_ENABLED':'1'}), \
             patch.object(api,'exercise_context',return_value={'context':'原文','images':[],
                 'reference':{'document_id':'verified-doc','image_refs':[]}}), \
             patch.object(api,'memory_for',return_value={'summary':'','preferences':{}}), \
             patch.object(api,'catalog',return_value={'version':'a'*64}), \
             patch('knowledge.grounded_citations.settings',return_value=None):
            result=api.ai_parts(q,[q['parts'][0]],{'other':'OTHER-PART-SECRET'},ctx.student_id,'hint',
                user_question=ctx.message,strategy_context=ctx)
        plan=result['teaching_strategy_plan']
        self.assertEqual(plan['primary_strategy'],'hint')
        self.assertEqual(plan['target_ref'],f"exercise:{q['id']}:{q['parts'][0]['id']}:{'a'*64}")
        self.assertEqual(tutor.quality_checker.check.call_args.args[2].strategy,'hint')
        messages=tutor.llm.chat.call_args.args[0]
        self.assertNotIn('OTHER-PART-SECRET',str(messages))
        self.assertIn('统一教学决策',messages[0]['content'])
        self.assertFalse(any(m['action']=='ask_check' for m in plan['moves']))

    def test_grading_does_not_enter_teaching_selector(self):
        api,q,tutor=self.setup_inputs();tutor.llm.chat_json.side_effect=RuntimeError('grading sentinel')
        with patch.dict('sys.modules',{'main':SimpleNamespace(orchestrator=tutor)}), \
             patch.dict('os.environ',{'ADAPTIVE_TUTORING_ENABLED':'1'}), \
             patch.object(api,'exercise_context',return_value={'context':'原文','images':[],'reference':{'image_refs':[]}}), \
             patch.object(api,'memory_for',return_value={'summary':'','preferences':{}}), \
             patch('agents.teaching_strategy.decide_for_context',side_effect=AssertionError('grade selected teaching')), \
             self.assertRaisesRegex(RuntimeError,'grading sentinel'):
            api.ai_parts(q,[q['parts'][0]],{},'s','grade')
