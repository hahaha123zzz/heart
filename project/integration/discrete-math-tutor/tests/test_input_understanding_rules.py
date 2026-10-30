"""状态优先、无模型规则与待确认偏好。"""
import unittest
from unittest.mock import Mock
from models.chat_request import ChatRequest
from models.task_context import TaskContext
from agents.input_understanding.service import understand
from tests.test_adaptive_tutoring import prior


def parse(message, state=None, **kwargs):
    context=TaskContext(student_id='s',session_id='x',message=message,tutoring=state or {})
    return understand(context,ChatRequest(student_id='s',session_id='x',request_id='r',message=message),**kwargs)


class InputRulesTests(unittest.TestCase):
    def test_compound_is_not_single_restore_and_needs_no_model(self):
        llm=Mock()
        result=parse('先解释“操作性定义”这个词，再回到原来的题，不要替我作答。',prior(pending=True),llm=llm)
        self.assertTrue(result.explain_then_resume)
        self.assertFalse(result.only_resume_question)
        self.assertIn('no_full_answer',result.tasks[0].constraints)
        llm.chat_json.assert_not_called()

    def test_negated_resume_is_not_executed(self):
        result=parse('不要回到原题，先解释操作性定义。',prior(pending=True))
        self.assertFalse(result.only_resume_question)
        self.assertFalse(result.explain_then_resume)

    def test_plain_resume_only_binds_current_question(self):
        result=parse('回到原来的题，我还没作答。',prior(pending=True))
        self.assertTrue(result.only_resume_question)
        self.assertEqual(result.references[-1].canonical_id,result.context.pending_question_id)

    def test_scopes_and_quotes_are_preserved(self):
        result=parse('以后详细一点，但这一题直接给答案：自变量是什么？',prior(pending=True))
        self.assertEqual([(d.scope,d.key) for d in result.directives],
                         [('persistent','answer_length'),('question','response_style')])
        self.assertTrue(result.directives[0].requires_confirmation)

    def test_semantic_classifier_cannot_replace_bindings(self):
        classifier=Mock();classifier.annotate.return_value=('test-v1',[
            dict(dimension='intent',label='explain',quote='解释',source='model')])
        result=parse('解释自变量',classifier=classifier)
        self.assertEqual(result.annotations[0].label,'explain')
        self.assertEqual(result.tasks[0].action,'explain_content')

    def test_no_private_answer_key_is_sent_to_classifier(self):
        classifier=Mock();classifier.annotate.return_value=('v1',[])
        parse('请解释',prior(pending=True),classifier=classifier)
        self.assertNotIn('PRIVATE-',str(classifier.annotate.call_args))

    def test_session_activity_binding_keeps_revision_without_advancing(self):
        message='回到刚才的学习安排'
        plan={'plan_id':'p','revision':3,'current_item_id':'a','path_id':None,'path_revision':None,'items':[]}
        context=TaskContext(student_id='s',session_id='x',message=message,session_study_plan=plan)
        request=ChatRequest(student_id='s',session_id='x',message=message)
        turn=understand(context,request)
        self.assertEqual(turn.tasks[0].action,'resume_learning_activity')
        self.assertEqual(turn.context.session_plan_revision,3)
        self.assertEqual(plan['current_item_id'],'a')
        request=request.model_copy(update={'message':'不要回到学习安排，解释信度'})
        self.assertNotEqual(understand(context,request).tasks[0].action,'resume_learning_activity')

    def test_multiple_state_changes_are_rejected_before_any_model_or_write(self):
        from agents.input_understanding.decision import decide
        model=Mock()
        turn=parse('确认学习计划，同时提交我的答案，我选B。',prior(pending=True),llm=model)
        self.assertEqual(decide(turn).status,'reject')
        model.chat_json.assert_not_called()


if __name__=='__main__':unittest.main()
