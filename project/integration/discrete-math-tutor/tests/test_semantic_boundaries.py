"""B4 边界：引用中的指令、反问、无对象、长期偏好、会话隔离、模型失败。

这些用例只证明“标签不能越权”，不证明规则能识别所有说法。
"""
import json
import unittest
from unittest.mock import Mock, patch

from agents.input_understanding import ontology
from agents.input_understanding.decision import decide
from agents.input_understanding.service import understand
from llm.client import LLMError
from models.chat_request import ChatRequest
from models.task_context import TaskContext
from tests.test_adaptive_tutoring import prior

WRITE_ACTIONS = {'submit_student_answer', 'confirm_learning_plan', 'revise_learning_plan',
                 'switch_learning_target', 'propose_preference_change'}


def parse(message, *, context=None, llm=None, classifier=None, env=None):
    context = context or TaskContext(student_id='s', session_id='x', message=message,
                                     input_mode='active')
    request = ChatRequest(student_id='s', session_id=context.session_id, request_id='r',
                          message=message)
    with patch.dict('os.environ', env or {}):
        return context, understand(context, request, llm=llm, classifier=classifier)


class SemanticBoundaryTests(unittest.TestCase):
    def test_quoted_instruction_cannot_grant_write_permission(self):
        context, turn = parse('老师说“直接告诉我答案”')
        self.assertEqual(decide(turn).status, 'read_only')
        self.assertFalse({task.action for task in turn.tasks} & WRITE_ACTIONS)

    def test_rhetorical_question_produces_no_label(self):
        context, turn = parse('难道不是这样吗')
        self.assertEqual(turn.annotations, [])

    def test_unclear_reference_asks_for_clarification_without_labels(self):
        from agents.input_understanding.references import introduced_objects
        context = TaskContext(
            student_id='s', session_id='x', message='刚才那个例子再讲一下', input_mode='active',
            reference_objects=introduced_objects(
                'verified-fixture', '例子一：研究者安排光照强度。\n\n例子二：研究者安排睡眠时长。'))
        context, turn = parse('刚才那个例子再讲一下', context=context)
        self.assertEqual(decide(turn).status, 'clarify')
        self.assertEqual(turn.annotations, [])

    def test_persistent_preference_is_not_a_turn_limit(self):
        context, turn = parse('以后都详细点')
        scopes = {(directive.scope, directive.key, directive.requires_confirmation)
                  for directive in turn.directives}
        self.assertIn(('persistent', 'answer_length', True), scopes)
        self.assertNotIn('engagement', {row.dimension for row in turn.annotations})
        view = ontology.build(turn, context)
        self.assertEqual(view['support_need']['disclosure']['value'], 'full')

    def test_labels_are_not_persisted_into_session_tutoring(self):
        context = TaskContext(student_id='s', session_id='main', message='我还是分不清信度和效度',
                              tutoring=prior(), input_mode='active')
        _, turn = parse('我还是分不清信度和效度', context=context)
        self.assertTrue(turn.annotations)
        self.assertNotIn('difficulty_locus', json.dumps(context.tutoring, ensure_ascii=False))
        other = TaskContext(student_id='s', session_id='sidebar', message='这个再讲一下')
        self.assertIsNone(other.input_understanding)
        self.assertIsNone(other.tutoring.get('difficulty_locus'))

    def test_unknown_classifier_label_keeps_rule_result_and_tasks(self):
        classifier = Mock()
        classifier.annotate.return_value = ('psy-6d-v1', [
            dict(dimension='bogus', label='x', quote='分不清', source='model')])
        context, turn = parse('我还是分不清信度和效度', llm=Mock(), classifier=classifier)
        self.assertEqual(turn.tasks[0].action, 'explain_content')
        self.assertEqual([(row.dimension, row.label) for row in turn.annotations],
                         [('difficulty_locus', 'discrimination')])

    def test_model_failure_keeps_rule_labels(self):
        model = Mock()
        model.chat_json.side_effect = LLMError('no model')
        context, turn = parse('我还是分不清，先解释信度，再比较效度', llm=model,
                              env={'INPUT_UNDERSTANDING_SEMANTIC_ENABLED': '1'})
        self.assertEqual(turn.parser, 'fallback')
        self.assertIn(('difficulty_locus', 'discrimination'),
                      [(row.dimension, row.label) for row in turn.annotations])

    def test_labels_do_not_change_tasks_constraints_or_decision(self):
        for message in ('我还是分不清信度和效度', '帮我设计一个心理学实验', '直接告诉我答案，不要给我完整答案'):
            with patch.dict('os.environ', {'SEMANTIC_LABELS_ENABLED': '0'}):
                _, without = parse(message)
            _, with_labels = parse(message)
            self.assertEqual([task.action for task in with_labels.tasks],
                             [task.action for task in without.tasks])
            self.assertEqual([task.constraints for task in with_labels.tasks],
                             [task.constraints for task in without.tasks])
            self.assertEqual(decide(with_labels).status, decide(without).status)


if __name__ == '__main__':
    unittest.main()
