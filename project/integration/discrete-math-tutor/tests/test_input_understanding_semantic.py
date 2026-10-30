"""复杂理解预算、规则保护与分类失败回退。"""
import unittest
from unittest.mock import Mock,patch
from models.chat_request import ChatRequest
from models.task_context import TaskContext
from agents.input_understanding.service import understand
from llm.client import LLMError


def parse(model,message='先解释自变量，再比较因变量，最后总结，不要出题。',classifier=None):
    context=TaskContext(student_id='s',session_id='x',message=message)
    request=ChatRequest(student_id='s',session_id='x',request_id='r',message=message)
    with patch.dict('os.environ',{'INPUT_UNDERSTANDING_SEMANTIC_ENABLED':'1'}):
        return understand(context,request,llm=model,classifier=classifier)


def candidate():
    return dict(tasks=[dict(task_frame_id='f1',action='explain_content',query='自变量'),
                       dict(task_frame_id='f2',action='compare_content',query='因变量',depends_on=['f1'])],
                directives=[],clarification_needed=False,unresolved=[])


class InputSemanticTests(unittest.TestCase):
    def test_one_call_preserves_rule_constraints(self):
        model=Mock();model.chat_json.return_value=candidate()
        turn=parse(model)
        self.assertEqual(turn.parser,'model');self.assertEqual(turn.model_calls,1)
        self.assertTrue(all('no_questions' in task.constraints for task in turn.tasks))
        self.assertEqual(model.chat_json.call_count,1)

    def test_simple_message_has_no_extra_model_call(self):
        model=Mock();parse(model,'什么是自变量？')
        model.chat_json.assert_not_called()

    def test_ordered_distinct_steps_are_resolved_but_a_simple_example_is_not(self):
        for message in ('先说明自变量，然后比较因变量，最后概括差异。','先解释自变量，再比较因变量。'):
            model=Mock();model.chat_json.return_value=candidate()
            self.assertEqual(parse(model,message).parser,'model')
            model.chat_json.assert_called_once()
        model=Mock();parse(model,'先解释自变量再举一个例子')
        model.chat_json.assert_not_called()

    def test_clarification_without_reference_does_not_invent_an_example(self):
        from agents.input_understanding.decision import clarification_result
        model=Mock();model.chat_json.return_value=candidate()|{'clarification_needed':True}
        turn=parse(model)
        result=clarification_result(turn,TaskContext(student_id='s',message=turn.envelope.raw_text))
        self.assertIn('具体对象或步骤',result['reply'])
        self.assertNotIn('例子',result['reply'])

    def test_model_cannot_drop_a_previously_resolved_example(self):
        from agents.input_understanding.references import introduced_objects
        message='先解释刚才那个例子，再比较因变量，最后总结。'
        context=TaskContext(student_id='s',session_id='x',message=message,
            reference_objects=introduced_objects('t','例子一：研究者操纵光照。'))
        request=ChatRequest(student_id='s',session_id='x',request_id='r',message=message)
        model=Mock();model.chat_json.return_value=candidate()
        with patch.dict('os.environ',{'INPUT_UNDERSTANDING_SEMANTIC_ENABLED':'1'}):
            turn=understand(context,request,llm=model)
        self.assertEqual(turn.parser,'fallback')
        self.assertEqual(turn.tasks[0].target_ref,'mention')
        model.chat_json.assert_called_once()

    def test_schema_failure_has_one_repair_and_stops(self):
        model=Mock();model.chat_json.side_effect=[{},{}]
        turn=parse(model)
        self.assertEqual(turn.parser,'fallback');self.assertEqual(turn.model_calls,2)
        self.assertEqual(model.chat_json.call_count,2)

    def test_model_cannot_create_approved_or_write_action(self):
        for task in (dict(task_frame_id='f1',action='switch_learning_target'),
                     dict(task_frame_id='f1',action='explain_content',state='completed')):
            model=Mock();model.chat_json.return_value=candidate()|{'tasks':[task]}
            turn=parse(model)
            self.assertEqual(turn.parser,'fallback')
            self.assertNotIn(turn.tasks[0].action,('switch_learning_target','submit_student_answer'))
            self.assertEqual(turn.tasks[0].state,'pending')
            self.assertEqual(model.chat_json.call_count,1)

    def test_fabricated_reference_rejected_and_never_executed(self):
        model=Mock();model.chat_json.return_value=candidate()|{'tasks':[
            dict(task_frame_id='f1',action='explain_content',target_ref='foreign')]}
        turn=parse(model)
        self.assertEqual(turn.parser,'fallback')
        self.assertIsNone(turn.tasks[0].target_ref)
        self.assertEqual(model.chat_json.call_count,1)

    def test_provider_or_classifier_failure_keeps_rule_result(self):
        model=Mock();model.chat_json.side_effect=LLMError('not available')
        classifier=Mock();classifier.annotate.side_effect=LLMError('no classifier')
        turn=parse(model,classifier=classifier)
        self.assertEqual(turn.parser,'fallback')
        self.assertEqual(turn.annotations,[])
        self.assertEqual(model.chat_json.call_count,1)

    def test_complex_parse_does_not_add_a_second_classifier_model(self):
        model=Mock();model.chat_json.return_value=candidate();classifier=Mock()
        turn=parse(model,classifier=classifier)
        self.assertEqual(turn.parser,'model')
        classifier.annotate.assert_not_called()

    def test_literal_quote_failure_is_not_repaired_as_a_format_error(self):
        model=Mock();model.chat_json.return_value=candidate()|{'directives':[
            dict(scope='turn',key='answer_length',value=1.,quote='根本没有这句话')]}
        turn=parse(model)
        self.assertEqual(turn.parser,'fallback')
        self.assertEqual(model.chat_json.call_count,1)

    def test_unresolved_semantics_are_not_reported_as_fully_resolved(self):
        model=Mock();model.chat_json.return_value=candidate()|{'unresolved':['需要补充比较对象']}
        self.assertEqual(parse(model).resolution_status,'partial')


if __name__=='__main__':unittest.main()
