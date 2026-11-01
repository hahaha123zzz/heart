"""规则标签：40 条标注、否定保护、与模型合并、不越权。"""
import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from agents.input_understanding import labels as labeler
from agents.input_understanding import ontology
from agents.input_understanding.service import understand
from models.chat_request import ChatRequest
from models.input_understanding import SemanticAnnotation
from models.task_context import TaskContext


def parse(message, *, model=None, classifier=None):
    context = TaskContext(student_id='s', session_id='x', message=message)
    request = ChatRequest(student_id='s', session_id='x', request_id='r', message=message)
    with patch.dict('os.environ', {'INPUT_UNDERSTANDING_SEMANTIC_ENABLED': '1' if model else '0'}):
        return understand(context, request, llm=model, classifier=classifier)


def candidate(**extra):
    data = dict(tasks=[dict(task_frame_id='f1', action='explain_content', query='信度'),
                       dict(task_frame_id='f2', action='explain_content', query='效度', depends_on=['f1'])],
                directives=[], clarification_needed=False, unresolved=[])
    return data | extra


def grouped(rows):
    result = {}
    for row in rows:
        result.setdefault(row.dimension, []).append(row.label)
    return result


class LabelRuleTests(unittest.TestCase):
    def test_40_curated_cases(self):
        path = Path(__file__).parent / 'fixtures/semantic_labels_v1.jsonl'
        cases = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
        self.assertEqual(len(cases), 40)
        for case in cases:
            with self.subTest(text=case['text']):
                rows = labeler.extract(case['text'])
                self.assertEqual(grouped(rows), case['labels'])
                for row in rows:
                    self.assertIn(row.quote, case['text'])
                    self.assertTrue(ontology.valid_label(row.dimension, row.label))
                    self.assertEqual(row.source, 'rule')

    def test_negated_answer_request_produces_no_label(self):
        self.assertEqual(labeler.extract('别直接给答案'), [])
        self.assertEqual(labeler.extract('不用告诉我答案'), [])

    def test_multilabel_cognitive_demand_keeps_text_order(self):
        rows = labeler.extract('分析这个实验是否合理，并设计改进方案')
        self.assertEqual([row.label for row in rows], ['analyze', 'evaluate', 'create'])

    def test_merge_caps_single_label_dimension(self):
        rows = labeler.merge([], [
            SemanticAnnotation(dimension='difficulty_locus', label='comprehension', quote='不懂', source='model'),
            SemanticAnnotation(dimension='difficulty_locus', label='discrimination', quote='分不清', source='model'),
        ])
        self.assertEqual(len(rows), 1)

    def test_merge_rejects_unknown_label(self):
        with self.assertRaises(ValueError):
            labeler.merge([], [dict(dimension='difficulty_locus', label='bored',
                                    quote='不懂', source='model')])


class LabelServiceTests(unittest.TestCase):
    def test_rules_reach_the_view_without_model_calls(self):
        turn = parse('我还是分不清信度和效度')
        self.assertEqual(turn.model_calls, 0)
        self.assertIn(('difficulty_locus', 'discrimination'),
                      [(row.dimension, row.label) for row in turn.annotations])
        view = ontology.build(turn, TaskContext(student_id='s', message='x'))
        self.assertEqual(view['learner_state']['difficulty_locus']['value'], 'discrimination')

    def test_labels_do_not_change_tasks_or_constraints(self):
        turn = parse('解释信度，不要给我完整答案')
        self.assertEqual(turn.tasks[0].action, 'explain_content')
        self.assertIn('no_full_answer', turn.tasks[0].constraints)
        self.assertNotIn('engagement', {row.dimension for row in turn.annotations})

    def test_model_labels_merge_into_the_same_call(self):
        model = Mock()
        model.chat_json.return_value = candidate(labels=[
            dict(dimension='cognitive_demand', label='comprehend', quote='解释', source='model')])
        turn = parse('我还是分不清信度和效度，先解释信度，再解释效度。', model=model)
        self.assertEqual(model.chat_json.call_count, 1)
        self.assertEqual(turn.parser, 'model')
        seen = {(row.dimension, row.label) for row in turn.annotations}
        self.assertIn(('difficulty_locus', 'discrimination'), seen)
        self.assertIn(('cognitive_demand', 'comprehend'), seen)

    def test_invalid_model_label_is_dropped_without_losing_the_turn(self):
        model = Mock()
        model.chat_json.return_value = candidate(labels=[
            dict(dimension='difficulty_locus', label='bored', quote='分不清', source='model')])
        turn = parse('我还是分不清信度和效度，先解释信度，再解释效度。', model=model)
        self.assertEqual(turn.parser, 'model')
        self.assertIn('semantic_label_rejected', turn.unresolved)
        self.assertNotIn('bored', [row.label for row in turn.annotations])

    def test_classifier_keeps_rule_labels_and_receives_missing_dimensions(self):
        classifier = Mock()
        classifier.annotate.return_value = ('psy-6d-v1', [
            dict(dimension='cognitive_demand', label='comprehend', quote='分不清', source='model')])
        turn = parse('我还是分不清信度和效度', model=Mock(), classifier=classifier)
        seen = {(row.dimension, row.label) for row in turn.annotations}
        self.assertIn(('difficulty_locus', 'discrimination'), seen)
        self.assertIn(('cognitive_demand', 'comprehend'), seen)
        missing = classifier.annotate.call_args.args[2]
        self.assertIn('cognitive_demand', missing)
        self.assertNotIn('difficulty_locus', missing)


if __name__ == '__main__':
    unittest.main()
