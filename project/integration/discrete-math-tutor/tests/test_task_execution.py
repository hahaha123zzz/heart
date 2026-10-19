"""任务消费与回答约束：模型替身、原始实体保留、既有教材调用链。"""
import json
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
from agents.task_execution import build_execution, TaskExecution
from agents.teaching_planner import TeachingPlan
from agents.response_generator import ResponseGenerator
from agents.quality_checker import QualityChecker, QualityResult
from models.task_understanding import TaskUnderstanding
from models.task_context import TaskContext, TaskObject
from models.student_state import StudentState
from tests import test_quality_guard as quality_fixtures
from knowledge.textbook import TextbookChunk


class TaskExecutionTests(unittest.TestCase):
    def test_accuracy_request_does_not_become_hint_scope(self):
        task=TaskUnderstanding(learning_intents=['explain','compare','hint'],answer_constraints=['no_full_answer'])
        execution=build_execution('请解释我框选的两个差别感觉阈限DL公式：X、St、PSE、N分别是什么，两个公式的参照点有什么区别？引用这个选区，不要编造实验数据。',task)
        self.assertFalse(execution.hint_only)
        self.assertEqual(execution.learning_intents,['explain','compare'])

    def test_accuracy_guard_preserves_explicit_hint_request(self):
        task=TaskUnderstanding(learning_intents=['explain','hint'],answer_constraints=['no_full_answer'])
        self.assertTrue(build_execution('请解释公式，只给提示，不要猜测。',task).hint_only)

    def test_accuracy_guard_preserves_outline_only_request(self):
        task=TaskUnderstanding(learning_intents=['explain'],answer_constraints=['no_full_answer'])
        self.assertTrue(build_execution('请解释公式，只说思路，不要编造数据。',task).hint_only)

    def test_distinguish_request_becomes_explanation_not_question(self):
        task=TaskUnderstanding(learning_intents=[],answer_constraints=[])
        execution=build_execution(
            '请结合教材区分自变量、因变量和额外变量，每类只讲一个要点，引用对应的教材依据。',task)
        self.assertIn('explain',execution.learning_intents)
        self.assertTrue(execution.explicit)

    def test_comparison_keeps_all_parts_and_matches_quality_length_budget(self):
        answer='比较说明。'*55+'两者均需控制额外变量。[1]'
        llm=Mock();llm.chat.return_value=answer
        execution=TaskExecution(learning_intents=['compare','explain'])
        plan=self.plan();execution.align(plan)
        with patch('agents.response_generator._library_guides',return_value={}):
            response=ResponseGenerator(llm).generate(StudentState(),plan,'比较两种设计的条件、适用情境和控制问题',[],task_execution=execution)
        self.assertEqual(response,answer)
        self.assertEqual(llm.chat.call_args.kwargs['max_tokens'],900)
        self.assertEqual(QualityChecker._rule_check(response,plan,{'task_comparison':True}),[])
        execution.answer_constraints=['hint_only']
        self.assertEqual(execution.reply_limit(200),200)
    def plan(self): return TeachingPlan(goal='解释',strategy='worked_example',action='explain',difficulty='medium')

    def test_explicit_requests_can_repeat_action_without_repeating_answer(self):
        context={'recent_moves':['direct_explanation']*3,'explicit_task':True,'previous_reply':'上一张图有四条边。'}
        self.assertEqual(QualityChecker._rule_check('当前图有五条边。',self.plan(),context),[])
        self.assertTrue(QualityChecker._rule_check('上一张图有四条边。',self.plan(),context))
        self.assertTrue(QualityChecker._rule_check('当前图有五条边。',self.plan(),dict(context,explicit_task=False)))
    def context(self, message):
        return TaskContext(student_id='guard-test',message=message,knowledge_point='新目标',objects=[
            TaskObject(id='one',kind='section',title='定理7.7',text='不应直接拼入检索的整节正文',chapter_id=7,section_id=3),
            TaskObject(id='two',kind='pdf_selection',title='定理7.2',text='奇数度顶点个数为偶数',chapter_id=7,section_id=1)])

    def test_original_formula_number_and_both_targets_are_preserved(self):
        message='比较定理7.7与定理7.2；A∧B 与 p∧q'
        context=self.context(message)
        task=TaskUnderstanding(learning_intents=['compare'],target_refs=['one','two'])
        execution=build_execution(message,task,context)
        self.assertTrue(execution.retrieval_query.startswith(message))
        self.assertEqual(execution.target_refs,['one','two'])
        self.assertIn('奇数度顶点',execution.retrieval_query)
        self.assertNotIn('整节正文',execution.retrieval_query)

    def test_server_hint_scope_still_wins_over_concise_verdict(self):
        context=TaskContext(student_id="guard-test",message="只判断对错",knowledge_point="图",
            objects=[TaskObject(id="visualization:g",kind="visualization",title="当前图",chapter_id=1,section_id=1)],
            graph_snapshot={"artifact_id":"g","answer_scope":"hint"})
        execution=build_execution("只判断对错",TaskUnderstanding(learning_intents=["check_answer"]),context)
        self.assertTrue(execution.hint_only)
        self.assertFalse(execution.verdict_only)

    def test_unknown_target_is_rejected(self):
        with self.assertRaises(ValueError): build_execution('问题',TaskUnderstanding(target_refs=['invented']),self.context('问题'))

    def test_hint_overrides_proof_and_worked_example(self):
        execution=TaskExecution(learning_intents=['proof','hint'],answer_constraints=['no_full_answer'])
        plan=self.plan(); self.assertTrue(execution.align(plan))
        self.assertEqual(plan.action,'give_hint');self.assertEqual(plan.strategy,'progressive_hinting')
        self.assertEqual(plan.hint_level,1);self.assertIn('不展开完整证明',execution.instructions())

    def test_example_order_and_comparison_are_explicit(self):
        execution=TaskExecution(learning_intents=['example','proof'],answer_constraints=['example_before_proof','include_prerequisites'])
        plan=self.plan();execution.align(plan)
        self.assertEqual(plan.action,'give_example')
        self.assertIn('先给相关具体例子',execution.instructions());self.assertIn('前置定义',execution.instructions())
        self.assertIn('辅助例子（非原书例题）', execution.instructions())
        compared=TaskExecution(learning_intents=['compare']);compared.align(plan)
        self.assertEqual(plan.strategy,'conceptual_comparison')

    def test_legacy_task_does_not_override_plan(self):
        plan=self.plan();before=plan.model_dump();self.assertFalse(TaskExecution().align(plan));self.assertEqual(before,plan.model_dump())

    def test_practice_uses_question_action(self):
        plan=self.plan();self.assertFalse(TaskExecution(learning_intents=['practice']).align(plan))
        self.assertEqual(plan.action,'ask_question')

    def test_generator_hint_does_not_expand_full_proof_budget(self):
        llm=Mock();llm.chat.return_value='先尝试应用度数关系。'
        generator=ResponseGenerator(llm);execution=TaskExecution(learning_intents=['hint','proof']);plan=self.plan();execution.align(plan)
        with patch('agents.response_generator._library_guides',return_value={}):
            generator.generate(StudentState(),plan,'完整证明只要提示',[],task_execution=execution)
        system=llm.chat.call_args.args[0][0]['content']
        self.assertIn('仅给一个知识点',system)
        self.assertNotIn('本轮明确请求完整证明思路',system)
        self.assertEqual(llm.chat.call_args.kwargs['max_tokens'],400)

    def test_semantic_quality_sees_task_constraints(self):
        llm=Mock();llm.mock=True;llm.chat_json.return_value={'passed':False,'issues':['提示泄露完整结论'],'suggestions':''}
        checker=QualityChecker(llm);execution=TaskExecution(learning_intents=['hint']);plan=self.plan();execution.align(plan)
        result=checker.check('由上述关系可立刻算得这个数值。',StudentState(),plan,'只给提示',task_execution=execution)
        self.assertFalse(result.passed)
        self.assertIn('没有出现答案标记',llm.chat_json.call_args.args[0][-1]['content'])

    def test_hint_answer_marker_is_rejected_before_semantic_call(self):
        llm=Mock();execution=TaskExecution(learning_intents=['hint']);plan=self.plan();execution.align(plan)
        result=QualityChecker(llm).check('正确答案是42',StudentState(),plan,'只给提示',task_execution=execution)
        self.assertFalse(result.passed);llm.chat_json.assert_not_called()

    def run_task(self, task, message='解释这个证明'):
        tutor=quality_fixtures.QualityGuardTests().tutor([QualityResult(passed=True)])
        tutor.conversation_router.route.return_value=task
        tutor.response_generator.generate.side_effect=['先看度数之间的关系。']
        context=self.context(message)
        source=TextbookChunk(source='教材.txt',section='小节',text='已知条件',terms=frozenset())
        with patch('orchestrator.retrieve_course',return_value=[source]) as retrieve,patch('orchestrator.retrieve_figures',return_value=[]),patch('orchestrator.expand_proof_sources',return_value=([source],None)),patch('orchestrator.enrich_sources',return_value=([source],None)),patch('orchestrator.complete_pdf_references',return_value=[]):
            result=tutor.handle_turn('guard-test',message,task_context=context)
        return tutor,result,retrieve

    def test_hint_survives_old_direct_explanation_strategy(self):
        tutor,result,_=self.run_task(TaskUnderstanding(student_move='question',learning_intents=['hint','proof'],answer_constraints=['hint_only']))
        self.assertEqual(result['teaching_plan']['action'],'give_hint')
        tutor.question_designer.design.assert_not_called()
        self.assertEqual(tutor.response_generator.generate.call_args.kwargs['task_execution'].learning_intents,['hint','proof'])
        self.assertEqual(tutor.quality_checker.check.call_args.kwargs['task_execution'].learning_intents,['hint','proof'])
        self.assertFalse(result['step_advanced'])

    def test_checked_object_is_used_in_retrieval_and_current_goal(self):
        tutor,result,retrieve=self.run_task(TaskUnderstanding(student_move='question',needs_context=True,learning_intents=['proof'],target_refs=['two']))
        self.assertIn('定理7.2',retrieve.call_args.args[0])
        self.assertEqual(retrieve.call_args.kwargs['preferred_types'], ('theorem','proof'))
        self.assertEqual(result['knowledge_point'],'新目标')
        tutor.conversation_router.route.assert_called_once()

    def test_example_first_not_overridden_by_explanation(self):
        tutor,result,_=self.run_task(TaskUnderstanding(student_move='question',learning_intents=['example','proof'],answer_constraints=['example_before_proof']))
        self.assertEqual(result['teaching_plan']['action'],'give_example')
        self.assertEqual(result['instructional_move']['instructional_move'],'worked_example')

    def test_comparison_evidence_gate_receives_both_resolved_objects(self):
        tutor,result,_=self.run_task(TaskUnderstanding(student_move='question',needs_context=True,learning_intents=['compare'],target_refs=['one','two']),message='比较这两个')
        checked=tutor.context_sufficiency.check.call_args.args[0]
        self.assertTrue(checked.startswith('比较这两个'))
        self.assertIn('定理7.7',checked);self.assertIn('定理7.2',checked)

    def test_example_then_proof_has_consistent_generation_and_quality_budget(self):
        execution=TaskExecution(learning_intents=['example','proof'],answer_constraints=['example_before_proof'])
        plan=self.plan();execution.align(plan)
        self.assertEqual(execution.reply_limit(200),480)
        self.assertEqual(QualityChecker._rule_check('推理。'*100,plan,{'task_proof':True}),[])
        self.assertTrue(QualityChecker._rule_check('推理。'*100,plan,{}))

    def test_proof_task_has_room_without_inventing_full_overview_request(self):
        llm=Mock();llm.chat.return_value='推理。'*100;plan=self.plan()
        execution=TaskExecution(learning_intents=['proof']);execution.align(plan)
        with patch('agents.response_generator._library_guides',return_value={}):
            response=ResponseGenerator(llm).generate(StudentState(),plan,'解释这个步骤',[],task_execution=execution)
        self.assertEqual(response,'推理。'*100);self.assertEqual(llm.chat.call_args.kwargs['max_tokens'],900)
        self.assertNotIn('本轮明确请求完整证明思路',llm.chat.call_args.args[0][0]['content'])

    def test_hint_does_not_get_full_proof_length_budget(self):
        execution=TaskExecution(learning_intents=['proof','hint']);self.assertFalse(execution.proof_requested)
        self.assertEqual(execution.reply_limit(200),200)


if __name__=='__main__':unittest.main()
