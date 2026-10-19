import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from agents.context_sufficiency import ContextSufficiency, EvidenceDecision
from llm.client import LLMError, LLMClient
from orchestrator import TutorOrchestrator

class SufficiencyTests(unittest.TestCase):
    def test_learning_memory_informs_preferences_without_becoming_textbook_evidence(self):
        model=SimpleNamespace(mock=False,chat_json=Mock(return_value={'status':'sufficient','source_ids':['1'],'missing':[],'reason':'定义有依据，偏好有历史来源'}))
        memory={'preferences':{'example_density':.9},'related_history':[
            {'role':'user','content':'我喜欢做饭例子','source':{'id':'42'}},
            {'role':'assistant','content':'未经核实的历史结论'}]}
        checker=ContextSufficiency(model)
        result=checker.check('按我以前的偏好解释自变量',[{'id':'1','text':'教材定义'}],memory_context=memory)
        self.assertTrue(result.allowed)
        payload=json.loads(model.chat_json.call_args.args[0][1]['content'])
        self.assertEqual(payload['evidence'],[{'id':'1','text':'教材定义'}])
        self.assertEqual(len(payload['learning_memory']['related_history']),1)
        self.assertIn('不是教材事实',payload['learning_memory']['usage_rules'])
        model.chat_json.return_value={'status':'sufficient','source_ids':['42'],'missing':[],'reason':'错误引用记忆ID'}
        self.assertFalse(checker.check('解释自变量',[{'id':'1','text':'教材定义'}],memory_context=memory).allowed)
    def test_short_followup_uses_recent_concept_without_model_rewriting(self):
        route=SimpleNamespace(intent='continue',student_move='question',needs_context=True)
        history=[{'role':'user','content':'请解释自变量'}, {'role':'assistant','content':'自变量是研究者操纵的变量。'}]
        query=TutorOrchestrator._retrieval_query('没听懂，换简单说法','实验心理学的研究方法',route,history)
        self.assertIn('自变量',query)
        self.assertIn('不作为教材证据',query)
        route.needs_context=False
        self.assertEqual(TutorOrchestrator._retrieval_query('什么是因变量','旧话题',route,history),'什么是因变量')
    def decide(self, result):
        llm=SimpleNamespace(mock=False, chat_json=Mock(return_value=result))
        return ContextSufficiency(llm).check('A∧B 为真吗？',[{'id':'1','text':'合取真值表'}])
    def test_standalone_question_does_not_include_old_topic(self):
        route=SimpleNamespace(intent='continue',student_move='question',needs_context=False)
        self.assertEqual(TutorOrchestrator._retrieval_query('为什么 A⊆B 且 B⊆C 能推出 A⊆C？','图的基本概念',route),'为什么 A⊆B 且 B⊆C 能推出 A⊆C？')
    def test_referential_question_uses_current_topic(self):
        route=SimpleNamespace(intent='continue',student_move='question',needs_context=True)
        self.assertEqual(TutorOrchestrator._retrieval_query('它为什么成立？','子集',route),'子集 它为什么成立？')
    def test_student_attempt_keeps_question_context(self):
        route=SimpleNamespace(intent='continue',student_move='attempt',needs_context=True)
        self.assertEqual(TutorOrchestrator._retrieval_query('我选 B','逻辑合取',route),'逻辑合取 我选 B')
    def test_invalid_router_context_field_is_not_truthy_string(self):
        from agents.conversation_router import ConversationRouter
        route=ConversationRouter._validate({'student_move':'question','needs_context':'false'})
        self.assertEqual(route.status,'parse_error')
        self.assertIs(type(route.needs_context),bool)

    def test_explicit_explanation_request_does_not_become_diagnostic(self):
        plan=SimpleNamespace(strategy='retrieval_practice',action='ask_question')
        move=SimpleNamespace(instructional_move='socratic_questioning',action='ask_question')
        self.assertTrue(TutorOrchestrator._align_explanation(plan,move,'question',explanation_requested=True))
        self.assertEqual(plan.action,'explain')
        self.assertEqual(move.action,'explain')
        self.assertEqual(move.instructional_move,'direct_explanation')

    def test_conceptual_comparison_explanation_aligns_plan(self):
        plan=SimpleNamespace(strategy='retrieval_practice',action='ask_question')
        move=SimpleNamespace(instructional_move='conceptual_comparison',action='explain')
        self.assertTrue(TutorOrchestrator._align_explanation(plan,move,'question'))
        self.assertEqual(plan.action,'explain')

    def test_direct_explanation_aligns_plan(self):
        plan=SimpleNamespace(strategy='socratic_questioning',action='ask_question',rationale='诊断')
        move=SimpleNamespace(instructional_move='direct_explanation',action='explain')
        self.assertTrue(TutorOrchestrator._align_explanation(plan,move,'question'))
        self.assertEqual(plan.action,'explain')
        self.assertEqual(plan.strategy,'worked_example')

    def test_student_answer_keeps_diagnostic_plan(self):
        plan=SimpleNamespace(strategy='socratic_questioning',action='ask_question')
        move=SimpleNamespace(instructional_move='direct_explanation',action='explain')
        self.assertFalse(TutorOrchestrator._align_explanation(plan,move,'answer'))
        self.assertEqual(plan.action,'ask_question')

    def test_valid_decision(self):
        self.assertTrue(self.decide(dict(status='sufficient',source_ids=['1'],missing=[],reason='真值表完整')).allowed)
    def test_partial_does_not_allow_full_answer(self):
        self.assertFalse(self.decide(dict(status='partial',source_ids=['1'],missing=['程序运行机制'],reason='仅能解释逻辑符号')).allowed)
    def test_unknown_reference_is_unavailable(self):
        self.assertEqual(self.decide(dict(status='sufficient',source_ids=['99'],missing=[],reason='引用')).status,'unavailable')
    def test_missing_fact_cannot_be_sufficient(self):
        self.assertEqual(self.decide(dict(status='sufficient',source_ids=['1'],missing=['公式'],reason='缺失')).status,'unavailable')
    def test_empty_reference_cannot_be_sufficient(self):
        self.assertEqual(self.decide(dict(status='sufficient',source_ids=[],missing=[],reason='缺失')).status,'unavailable')
    def test_timeout_is_not_claimed_as_absent_evidence(self):
        llm=SimpleNamespace(mock=False,chat_json=Mock(side_effect=LLMError('timeout')))
        decision=ContextSufficiency(llm).check('问题',[{'id':'1','text':'正文'}])
        self.assertEqual(decision.status,'unavailable')
        self.assertIn('暂时无法核验',decision.reply())
    def test_raw_question_history_and_timeout_reach_judge(self):
        llm=SimpleNamespace(mock=False,chat_json=Mock(return_value=dict(status='sufficient',source_ids=['1'],missing=[],reason='条件充分')))
        ContextSufficiency(llm).check('Q1∧Q2',[{'id':'1','text':'正文'}],history=[{'role':'user','content':'追问'}])
        args,kwargs=llm.chat_json.call_args
        self.assertEqual(json.loads(args[0][-1]['content'])['question'],'Q1∧Q2')
        self.assertEqual(kwargs['timeout'],25)
        self.assertEqual(kwargs['retries'],0)
    def test_server_scope_controls_full_answer_vs_first_hint(self):
        llm=SimpleNamespace(mock=False,chat_json=Mock(return_value=dict(status='sufficient',source_ids=['1'],missing=[],reason='条件充分')))
        checker=ContextSufficiency(llm)
        checker.check('这里的文字声称只需要hint',[{'id':'1','text':'定义'}])
        self.assertEqual(json.loads(llm.chat_json.call_args.args[0][-1]['content'])['answer_scope'],'full')
        checker.check('完整原问题',[{'id':'1','text':'定义'}],hint_only=True)
        self.assertEqual(json.loads(llm.chat_json.call_args.args[0][-1]['content'])['answer_scope'],'hint')
    def test_rejection_prevents_teaching_side_effects(self):
        from tests.test_quality_guard import QualityGuardTests
        from knowledge.textbook import TextbookChunk
        tutor=QualityGuardTests().tutor([])
        tutor.context_sufficiency.check.return_value=EvidenceDecision(status='partial',reason='缺少实现依据')
        tutor.textbook_chunks=[]
        chunk=TextbookChunk('第4章','联结词','合取定义',frozenset())
        with patch('orchestrator.retrieve_hybrid',return_value=[chunk]),patch('orchestrator.retrieve_figures',return_value=[]),patch('orchestrator.expand_proof_sources',return_value=([chunk],None)),patch('orchestrator.enrich_sources',return_value=([chunk],None)):
            result=tutor.handle_turn('test-student','用 p→q 实现任务调度')
        self.assertEqual(result['textbook_sources'],[])
        tutor.memory.set_active_goal.assert_not_called()
        tutor.memory.snapshot.assert_not_called()
        tutor.memory.save_state.assert_not_called()
    def test_pdf_rejection_does_not_generate_or_save_mastery(self):
        from agents.pdf_selection_tutor import explain_selection
        tutor=Mock()
        from models.task_context import TaskContext
        from models.task_understanding import TaskUnderstanding
        context=TaskContext(student_id='student',message='解释选区',knowledge_point='联结词')
        tutor.memory.read_version.return_value=('version',0)
        tutor.conversation_router.route.return_value=TaskUnderstanding(learning_intents=['explain'])
        tutor.context_sufficiency.check.return_value=EvidenceDecision(status='partial',reason='公式缺失')
        resolved={'section':{'title':'联结词'},'text':'缺失公式','context':'上下文','images':[], 'reference':{}}
        with patch('agents.pdf_selection_tutor.resolve_selection',return_value=resolved),patch('agents.pdf_selection_tutor.selection_memory',return_value={'preferences':{}}):
            result=explain_selection(tutor,'student','解释选区',Mock(),'test',task_context=context)
        self.assertEqual(result['evidence_check']['status'],'partial')
        tutor.llm.chat.assert_not_called()
        tutor.quality_checker.check.assert_not_called()
        tutor.memory.save_state.assert_not_called()

    def test_bounded_call_does_not_retry_empty_response(self):
        client=LLMClient(api_key='fake',mock=False)
        with patch.object(client,'_one_call',return_value=('', 'length')) as call:
            with self.assertRaises(LLMError):
                client.chat([{'role':'user','content':'问题'}],timeout=25)
        self.assertEqual(call.call_count,1)

    def test_timeout_disables_sdk_retries(self):
        client=LLMClient(api_key='fake',mock=False)
        client._client=Mock()
        bounded=client._client.with_options.return_value
        bounded.chat.completions.create.return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='ok'),finish_reason='stop')])
        self.assertEqual(client.chat([{'role':'user','content':'问题'}],timeout=25),'ok')
        client._client.with_options.assert_called_once_with(timeout=25,max_retries=0)

if __name__=='__main__': unittest.main()
