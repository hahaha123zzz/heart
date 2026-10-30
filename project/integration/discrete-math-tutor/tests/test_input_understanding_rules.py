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


if __name__=='__main__':unittest.main()
