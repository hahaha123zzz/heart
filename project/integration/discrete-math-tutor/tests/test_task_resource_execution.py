"""选区、小题与按钮任务消费；隔离数据库和模型。"""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from sqlalchemy import select
from tests import test_clarification_tasks as fixtures
from agents.pdf_selection_tutor import explain_selection
from agents.exercise_task_tutor import explain_exercise
from agents.task_context_builder import TaskContextBuilder
from agents.task_execution import TaskExecution
from agents.quality_checker import QualityChecker, QualityResult
from models.task_understanding import TaskUnderstanding
from models.task_context import TaskContext, TaskObject, ExerciseTarget
from models.chat_request import ChatRequest
from database.models import ExerciseDraftRow, ExerciseHelpRow
from llm.client import LLMError
import practice_api as practice


class TaskResourceExecutionTests(unittest.TestCase):
    setUp = fixtures.ClarificationTests.setUp
    tearDown = fixtures.ClarificationTests.tearDown
    count = fixtures.ClarificationTests.count

    def pdf_tutor(self, quality):
        tutor=SimpleNamespace(memory=self.memory,llm=Mock(),conversation_router=Mock(),context_sufficiency=Mock(),quality_checker=Mock())
        tutor.llm.chat.return_value='先考虑每条边对度数的贡献。'
        tutor.quality_checker.check.return_value=quality
        tutor.context_sufficiency.check.return_value=SimpleNamespace(allowed=True,model_dump=lambda:{})
        tutor.conversation_router.route.return_value=TaskUnderstanding(student_move='question',learning_intents=['hint','proof'],answer_constraints=['hint_only'],target_refs=['selection-current'])
        message='这个证明只要提示'
        context=TaskContext(student_id='s',message=message,knowledge_point='图',objects=[TaskObject(id='selection-current',kind='pdf_selection',title='图',chapter_id=7,section_id=1)])
        ref={'document_id':'book','version':'v','chapter_id':7,'section_id':1,'section_title':'图','source':'教材','image_refs':[],'rects':[{'page':4}]}
        resolved={'section':{'title':'图'},'text':'度数定理','context':'教材上下文','images':[],'reference':ref}
        selection=SimpleNamespace(document_id='book',rects=[SimpleNamespace(page=4)])
        return tutor,context,resolved,selection

    def pdf_run(self,tutor,context,resolved,selection):
        with patch('agents.pdf_selection_tutor.selection_memory',return_value={'preferences':{},'summary':'暂无记录'}):
            return explain_selection(tutor,'s',context.message,selection,'production',task_context=context,resolved_selection=resolved)

    def test_pdf_hint_uses_hint_plan_and_keeps_reference(self):
        tutor,context,resolved,selection=self.pdf_tutor(QualityResult(passed=True))
        result=self.pdf_run(tutor,context,resolved,selection)
        self.assertEqual(tutor.quality_checker.check.call_args.args[2].action,'give_hint')
        self.assertIn('不展开完整证明',tutor.llm.chat.call_args.args[0][0]['content'])
        self.assertEqual(result['selection_ref']['rects'][0]['page'],4)
        self.assertEqual(self.count(fixtures.ConversationRow),2)

    def test_pdf_contradictory_quality_does_not_publish(self):
        tutor,context,resolved,selection=self.pdf_tutor(QualityResult(passed=True,issues=['泄露完整答案']))
        with self.assertRaises(LLMError): self.pdf_run(tutor,context,resolved,selection)
        self.assertEqual(self.count(fixtures.ConversationRow),0)

    def test_pdf_selection_passes_resolved_crops_to_generation_and_quality(self):
        tutor,context,resolved,selection=self.pdf_tutor(QualityResult(passed=True))
        images=[Path('chapter_02/page-2-crop.png')]
        resolved['images']=images
        with patch('knowledge.grounded_citations.settings', return_value=None), \
                patch.dict('os.environ', {'VISUALIZATION_ON_DEMAND': '0'}):
            self.pdf_run(tutor,context,resolved,selection)
        self.assertEqual(tutor.llm.chat.call_args.kwargs['image_paths'],images)
        self.assertEqual(tutor.quality_checker.check.call_args.kwargs['figure_images'],images)
        self.assertEqual(tutor.context_sufficiency.check.call_args.kwargs['image_paths'],images)

    def practice_tutor(self):
        tutor=SimpleNamespace(memory=self.memory,llm=Mock(),quality_checker=Mock(),conversation_router=Mock())
        tutor.quality_checker.check.return_value=QualityResult(passed=True)
        tutor.llm.chat_json.return_value={'reply':'先应用单元素集合的定义。'}
        return tutor

    def test_hint_quality_failure_hides_draft_and_sources(self):
        q=practice.question('ex-01-01-003');part=q['parts'][0];tutor=self.practice_tutor()
        tutor.quality_checker=QualityChecker(tutor.llm);tutor.llm.mock=True
        tutor.llm.chat_json.side_effect=[{'reply':'直接得出最终结论。'},{'passed':False,'issues':['完整结论泄露'],'suggestions':''}]
        with patch.dict(sys.modules,{'main':SimpleNamespace(orchestrator=tutor)}),patch.object(practice,'exercise_context',return_value={'context':'教材','images':[],'reference':{'image_refs':[]}}),patch.object(practice,'memory_for',return_value={'summary':'无记录'}):
            result=practice.ai_parts(q,[part],{},'s','hint')
        self.assertEqual(result['answer_status'],'quality_rejected')
        self.assertNotIn('最终结论',result['reply']);self.assertEqual(result['image_refs'],[])

    def test_button_has_explicit_task_without_classification(self):
        q=practice.question('ex-01-01-003');version=practice.catalog()['version'];tutor=self.practice_tutor()
        body=practice.HelpRequest(student_id='s',version=version,part_id='p1',action='hint')
        with patch.dict(sys.modules,{'main':SimpleNamespace(orchestrator=tutor)}),patch.object(practice,'student',return_value='s'),patch.object(practice,'ai_parts',return_value={'reply':'先看集合定义'}) as generate:
            practice.help_question(q['id'],body)
        execution=generate.call_args.kwargs['task_execution']
        self.assertTrue(execution.hint_only)
        self.assertEqual(execution.target_refs,[f"exercise:{q['id']}:p1:{version}"])
        tutor.conversation_router.route.assert_not_called()

    def test_practice_payload_contains_only_selected_part_answers(self):
        q=practice.question('ex-01-01-003');part=q['parts'][0];tutor=self.practice_tutor()
        with patch.dict(sys.modules,{'main':SimpleNamespace(orchestrator=tutor)}),patch.object(practice,'exercise_context',return_value={'context':'教材','images':[],'reference':{'image_refs':[]}}),patch.object(practice,'memory_for',return_value={'summary':'无记录'}):
            practice.ai_parts(q,[part],{part['id']:'自己的答案','other':'另一个小题的秘密'},'s','hint')
        payload=json_loads(tutor.llm.chat_json.call_args.args[0][-1]['content'])
        self.assertEqual(payload['student_answers'],{part['id']:'自己的答案'})
        self.assertEqual(tutor.quality_checker.check.call_args.args[2].action,'give_hint')

    def exercise_request(self, intents):
        q=practice.question('ex-01-01-001');version=practice.catalog()['version'];tutor=self.practice_tutor()
        request=ChatRequest(student_id='s',account_type='production',message='只提示这个小题',exercise_target=ExerciseTarget(question_id=q['id'],part_id='p1',version=version))
        context=TaskContextBuilder().build(student_id='s',message=request.message,knowledge_point=q['knowledge_point'],exercise_target=request.exercise_target)
        tutor.conversation_router.route.return_value=TaskUnderstanding(student_move='question',learning_intents=intents,target_refs=[context.objects[0].id])
        return tutor,request,context

    def test_chat_exercise_uses_current_students_draft_and_routes_once(self):
        tutor,request,context=self.exercise_request(['hint'])
        with self.factory.begin() as session:
            session.add(ExerciseDraftRow(student_id='s',question_id=request.exercise_target.question_id,version=request.exercise_target.version,answers={'p1':['A'],'p2':['B']}))
        with patch.object(practice,'ai_parts',return_value={'reply':'只考虑小题1的条件'}) as generate:
            result=explain_exercise(tutor,request,context,lambda *args:None,lambda:None)
        self.assertEqual(generate.call_args.args[2],{'p1':['A']})
        self.assertEqual(generate.call_args.args[4],'hint')
        tutor.conversation_router.route.assert_called_once()
        self.assertFalse(result['step_advanced'])
        self.assertEqual(self.count(ExerciseHelpRow),1)

    def test_chat_check_answer_without_draft_does_not_invent_answer(self):
        tutor,request,context=self.exercise_request(['check_answer'])
        with patch.object(practice,'ai_parts') as generate:
            result=explain_exercise(tutor,request,context,lambda *args:None,lambda:None)
        self.assertEqual(result['answer_status'],'answer_required');generate.assert_not_called()

    def test_clarified_exercise_never_generates_before_slots_are_filled(self):
        tutor,request,context=self.exercise_request(['hint'])
        with patch.object(practice,'ai_parts') as generate:
            result=explain_exercise(tutor,request,context,lambda *args:{'answer_status':'awaiting_clarification'},lambda:None)
        self.assertEqual(result['answer_status'],'awaiting_clarification');generate.assert_not_called()

    def test_failed_hint_not_recorded_as_received_help(self):
        q=practice.question('ex-01-01-003');tutor=self.practice_tutor()
        body=practice.HelpRequest(student_id='s',version=practice.catalog()['version'],part_id='p1',action='hint')
        with patch.dict(sys.modules,{'main':SimpleNamespace(orchestrator=tutor)}),patch.object(practice,'student',return_value='s'),patch.object(practice,'ai_parts',return_value={'reply':'本次未通过核对','answer_status':'quality_rejected'}):
            result=practice.help_question(q['id'],body)
        self.assertEqual(result['answer_status'],'quality_rejected');self.assertEqual(self.count(ExerciseHelpRow),0)
        self.assertEqual(self.count(fixtures.ConversationRow),0)

    def test_pdf_cannot_silently_explain_a_different_historical_selection(self):
        tutor,context,resolved,selection=self.pdf_tutor(QualityResult(passed=True))
        context.objects.append(TaskObject(id='selection-old',kind='pdf_selection',title='另一个图',chapter_id=7,section_id=2))
        tutor.conversation_router.route.return_value=TaskUnderstanding(student_move='question',learning_intents=['explain'],target_refs=['selection-old'])
        result=self.pdf_run(tutor,context,resolved,selection)
        self.assertEqual(result['answer_status'],'unsupported_task');tutor.llm.chat.assert_not_called()

    def test_proof_exercise_explanation_uses_proof_budget_and_check(self):
        q=next(q for q in practice.catalog()['questions'] if any(p['type']=='proof' for p in q['parts']))
        part=next(p for p in q['parts'] if p['type']=='proof');tutor=self.practice_tutor()
        with patch.dict(sys.modules,{'main':SimpleNamespace(orchestrator=tutor)}),patch.object(practice,'exercise_context',return_value={'context':'教材','images':[],'reference':{'image_refs':[]}}),patch.object(practice,'memory_for',return_value={'summary':'无记录'}):
            practice.ai_parts(q,[part],{},'s','explain')
        execution=tutor.quality_checker.check.call_args.kwargs['task_execution']
        self.assertTrue(execution.proof_requested);self.assertEqual(execution.reply_limit(200),480)
        self.assertIn('核对前提与推导',tutor.llm.chat_json.call_args.args[0][0]['content'])


def json_loads(value):
    import json
    return json.loads(value)

if __name__=='__main__':unittest.main()
