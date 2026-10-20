"""预算、草稿完整性和修订边界；不依赖旧数学题库或 PDF。"""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from agents.reply_budget import reply_budget
from agents.response_generator import ResponseGenerator
from agents.quality_checker import QualityChecker, QualityResult
from agents.task_execution import TaskExecution
from agents.teaching_planner import TeachingPlan
from agents.pdf_selection_tutor import explain_selection
from models.student_state import StudentState
from models.task_context import TaskContext
from models.task_understanding import TaskUnderstanding
from tests import test_quality_guard as fixtures
from llm.client import LLMClient, LLMError


class ReplyBudgetTests(unittest.TestCase):
    def test_detailed_plan_budget_is_shared_and_hint_stays_short(self):
        budget = reply_budget('请给出全书详细学习计划', preferences={'answer_length': 0})
        self.assertEqual((budget.target, budget.maximum, budget.max_tokens), (1800, 2400, 4800))
        self.assertLess(reply_budget('全书详细学习计划，只给提示', action='give_hint').maximum, 300)

    def test_structured_q5_plan_projection_keeps_last_objective(self):
        from agents.q5_runtime import Q5Runtime
        proposal = {'modules': [{'name': f'第{i}章', 'objectives': [
            {'name': f'目标{i}-{j}', 'source_refs': [{'title': f'来源{i}-{j}'}]}
            for j in range(12)]} for i in range(1, 12)]}
        rendered = Q5Runtime.format_plan(None, proposal)
        self.assertIn('目标11-11', rendered)
        self.assertEqual(rendered.count('（来源：'), 132)

    def plan(self,action='explain'):
        return TeachingPlan(goal='实验设计',strategy='worked_example',action=action,difficulty='easy')

    def test_explicit_complete_answer_overrides_old_short_preference(self):
        for text in ['请完整解释双盲的条件与原因','请详细说明两类偏差','请分别说明分组和控制变量']:
            with self.subTest(text=text):
                budget=reply_budget(text,preferences={'answer_length':0})
                self.assertEqual((budget.target,budget.maximum),(480,500))
        self.assertEqual(reply_budget('解释双盲',preferences={'answer_length':0}).maximum,160)
        self.assertEqual(reply_budget(execution=TaskExecution(preferences={'answer_length':0.})).maximum,160)

    def test_hint_stays_bounded_even_when_message_requests_full_proof(self):
        execution=TaskExecution(learning_intents=['hint','proof','compare'],answer_constraints=['hint_only'])
        budget=reply_budget('完整解释证明并比较，只给提示',execution=execution,action='give_hint')
        self.assertEqual((budget.target,budget.maximum),(200,260))
        self.assertTrue(execution.hint_only)

    def test_multi_part_request_has_room(self):
        budget = reply_budget("请说明操作性自变量与选择性自变量的区别，并说明按年龄分组的变量是否一定不是自变量。")
        self.assertGreaterEqual(budget.maximum, 360)

    def test_symbol_list_and_two_formula_request_has_room(self):
        budget = reply_budget(
            "请解释两个差别感觉阈限DL公式的X、St、PSE、N与参照点区别，不要编造实验数据。")
        self.assertGreaterEqual(budget.maximum, 500)

    def test_options_and_multiple_intents_have_room(self):
        self.assertGreaterEqual(reply_budget(question_options=True).maximum,420)
        self.assertEqual(reply_budget(execution=TaskExecution(learning_intents=['example','explain'])).maximum,500)

    def test_long_draft_reaches_checker_without_losing_last_object_or_citation(self):
        draft='第一部分：'+('讲解条件。'*60)+'第二部分：不能从相关直接推出因果。[1]'
        llm=Mock();llm.mock=True;llm.chat.return_value=draft
        reply=ResponseGenerator(llm).generate(StudentState(),self.plan(),'解释关系',[])
        self.assertEqual(reply,draft)
        quality=QualityChecker(llm).check(reply,StudentState(),self.plan(),'解释关系',textbook_excerpts='[1] 相关不等于因果')
        self.assertFalse(quality.passed)
        self.assertIn('压缩重复表达',quality.issues[0])
        llm.chat_json.assert_not_called()

    def test_generator_and_checker_use_identical_budget_for_detail_and_preferences(self):
        llm=Mock();llm.mock=True;llm.chat.return_value='条件。'*100;llm.chat_json.return_value={'passed':True,'issues':[]}
        execution=TaskExecution(learning_intents=['explain'],preferences={'answer_length':0.})
        message='请完整解释实验设计的条件和原因'
        response=ResponseGenerator(llm).generate(StudentState(),self.plan(),message,[],learner_preferences=execution.preferences,task_execution=execution)
        self.assertIn('可到500字',llm.chat.call_args.args[0][0]['content'])
        self.assertTrue(QualityChecker(llm).check(response,StudentState(),self.plan(),message,task_execution=execution).passed)
        self.assertIn('可到500字',llm.chat_json.call_args.args[0][1]['content'])

    def test_actual_retry_receives_full_previous_draft_and_feedback(self):
        helper=fixtures.QualityGuardTests()
        tutor=helper.tutor([QualityResult(passed=False,issues=['回复过长，压缩重复表达']),QualityResult(passed=True)])
        tutor.response_generator.generate.side_effect=['需要压缩的原始草稿','两部分都保留的修订稿']
        result=helper.run_turn(tutor)
        calls=tutor.response_generator.generate.call_args_list
        self.assertIsNone(calls[0].kwargs['revision_draft'])
        self.assertEqual(calls[1].kwargs['revision_draft'],'需要压缩的原始草稿')
        self.assertEqual(result['reply'],'两部分都保留的修订稿')
        tutor.memory.commit_learning_turn.assert_called_once()

    def test_pdf_selection_checks_entire_draft_then_saves_only_revised_answer(self):
        tutor=SimpleNamespace(memory=Mock(),llm=Mock(),conversation_router=Mock(),context_sufficiency=Mock(),quality_checker=Mock())
        tutor.memory.read_version.return_value=('v',0);tutor.memory.append_exchange.return_value='conversation'
        tutor.conversation_router.route.return_value=TaskUnderstanding(student_move='question',learning_intents=['explain'])
        tutor.context_sufficiency.check.return_value=SimpleNamespace(allowed=True,model_dump=lambda:{})
        long='说明。'*100+'第二部分仍完整。[1]';revised='两部分完整的修订说明。[1]'
        tutor.llm.chat.side_effect=[long,revised]
        tutor.quality_checker.check.side_effect=[QualityResult(passed=False,issues=['回复过长']),QualityResult(passed=True)]
        context=TaskContext(student_id='s',message='解释选中内容',knowledge_point='实验设计')
        reference={'source':'教材','image_refs':[],'chapter_id':2,'section_id':4,'section_title':'实验设计'}
        resolved={'section':{'title':'实验设计'},'text':'教材定义','context':'教材条件','images':[],'reference':reference,
                  'record':{'document_id':'doc','version':'v','chapter_id':2,'source':'教材'}}
        selection=SimpleNamespace(document_id='book',rects=[SimpleNamespace(page=1)])
        with patch('knowledge.grounded_citations.settings',return_value=None),patch('agents.pdf_selection_tutor.selection_memory',return_value={'preferences':{},'summary':''}),patch.dict('os.environ',{'VISUALIZATION_ON_DEMAND':'0'}):
            result=explain_selection(tutor,'s',context.message,selection,'production',task_context=context,resolved_selection=resolved)
        self.assertEqual(tutor.quality_checker.check.call_args_list[0].args[0],long)
        self.assertIn(long,tutor.llm.chat.call_args_list[1].args[0][1]['content'])
        self.assertEqual(result['reply'],revised)
        self.assertEqual(tutor.memory.append_exchange.call_args.args[2],revised)

    def test_gateway_rejects_nonempty_text_cut_short_by_provider(self):
        client=LLMClient(api_key='test-placeholder',mock=False)
        client._one_call=Mock(return_value=('第一部分。第二部分尚未', 'length'))
        with self.assertRaisesRegex(LLMError,'未完成回答'):
            client.chat([{'role':'user','content':'解释两部分'}])
        client._one_call.assert_called_once()

    def test_gateway_empty_output_retry_must_finish(self):
        for reason in ['stop','length']:
            with self.subTest(reason=reason):
                client=LLMClient(api_key='test-placeholder',mock=False)
                client._one_call=Mock(side_effect=[('', 'length'),('第二次回答',reason)])
                if reason=='length':
                    with self.assertRaises(LLMError):client.chat([{'role':'user','content':'解释'}])
                else:self.assertEqual(client.chat([{'role':'user','content':'解释'}]),'第二次回答')
                self.assertEqual(client._one_call.call_count,2)


if __name__=='__main__':unittest.main()
