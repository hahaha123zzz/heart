"""六维只读视图：不调模型、不写状态、缺数据写 null。"""
import json
import unittest
from typing import get_args

from agents.input_understanding import ontology
from agents.input_understanding.adapters import final_summary
from agents.input_understanding.service import understand
from models.chat_request import ChatRequest
from models.input_understanding import Action, GroundedTurn
from models.task_context import TaskContext

PENDING = {'stage': 'practice',
           'progress': {'pending_question': {'question_id': 'q1', 'options': []}}}


def turn_for(message, *, tutoring=None, preferences=None):
    context = TaskContext(student_id='s', session_id='x', message=message,
                          tutoring=tutoring or {}, preferences=preferences or {},
                          input_mode='active')
    request = ChatRequest(student_id='s', session_id='x', request_id='r', message=message)
    turn = understand(context, request)
    context.input_understanding = turn
    return context, turn


def annotate(turn, dimension, label, quote):
    data = turn.model_dump()
    data['annotations'] = [*data['annotations'],
                           {'dimension': dimension, 'label': label, 'quote': quote, 'source': 'rule'}]
    data['ontology_version'] = ontology.version()
    return GroundedTurn.model_validate(data)


class OntologyViewTests(unittest.TestCase):
    def test_view_exposes_six_dimensions(self):
        context, turn = turn_for('解释自变量')
        view = ontology.build(turn, context)
        self.assertEqual(view['ontology_version'], 'psy-6d-v1')
        for name in ('request_intent', 'cognitive_demand', 'learner_state',
                     'content_target', 'support_need', 'teaching_stage'):
            self.assertIn(name, view)
        self.assertEqual(view['request_intent']['primary'], 'knowledge_query')

    def test_every_action_maps_to_a_registered_intent(self):
        registered = set(ontology.registry()['dimensions']['request_intent']['values'])
        for action in get_args(Action):
            self.assertIn(ontology.intent_for(action), registered, action)
        self.assertEqual(ontology.intent_for('clarify_reference'), 'unclear')

    def test_textbook_target_overrides_intent(self):
        self.assertEqual(ontology.intent_for('explain_content', ref_kind='pdf_selection'),
                         'textbook_interaction')
        self.assertEqual(ontology.intent_for('explain_content', ref_kind='section'),
                         'knowledge_query')

    def test_pending_hint_is_exercise_not_repair(self):
        self.assertEqual(ontology.intent_for('provide_hint', has_pending=True), 'exercise_interaction')
        self.assertEqual(ontology.intent_for('provide_hint', has_pending=False), 'repair')

    def test_labels_fill_learner_state_and_shrink_missing(self):
        context, turn = turn_for('我还是分不清信度和效度')
        self.assertNotIn('difficulty_locus', ontology.missing_labels(turn))
        self.assertIn('self_report', ontology.missing_labels(turn))
        turn = annotate(turn, 'self_report', 'confused', '分不清')
        self.assertNotIn('difficulty_locus', ontology.missing_labels(turn))
        self.assertNotIn('self_report', ontology.missing_labels(turn))
        view = ontology.build(turn, context)
        self.assertEqual(view['learner_state']['difficulty_locus']['value'], 'discrimination')
        self.assertEqual(view['learner_state']['difficulty_locus']['source'], 'rule')
        self.assertEqual(view['learner_state']['self_report']['source'], 'rule')

    def test_cognitive_demand_is_multi_label_in_text_order(self):
        context, turn = turn_for('分析这个实验是否合理，并设计改进方案')
        view = ontology.build(turn, context)
        self.assertEqual(view['cognitive_demand']['values'], ['analyze', 'evaluate', 'create'])

    def test_disclosure_comes_from_constraints(self):
        context, turn = turn_for('解释信度，不要给我完整答案')
        view = ontology.build(turn, context)
        self.assertEqual(view['support_need']['disclosure']['value'], 'no_answer')
        self.assertEqual(view['support_need']['disclosure']['source'], 'constraint')

    def test_verbosity_uses_profile_when_no_turn_directive(self):
        context, turn = turn_for('解释自变量', preferences={'answer_length': 0.0})
        view = ontology.build(turn, context)
        self.assertEqual(view['support_need']['verbosity']['value'], 'short')
        self.assertEqual(view['support_need']['verbosity']['source'], 'profile')

    def test_turn_directive_outranks_profile(self):
        # 本轮 answer_length 指令要到 P2 才解析；这里单独校验优先级规则。
        self.assertEqual(ontology._pick({'answer_length': 0.9}, {'answer_length': 0.1},
                                        'answer_length', ('short', 'normal', 'long')),
                         ('long', 'turn'))
        self.assertEqual(ontology._pick({}, {'answer_length': 0.5},
                                        'answer_length', ('short', 'normal', 'long')),
                         ('normal', 'profile'))

    def test_attempt_is_read_not_guessed(self):
        context, turn = turn_for('解释自变量', tutoring=PENDING)
        self.assertEqual(ontology.build(turn, context)['learner_state']['attempt']['value'], 'awaiting')
        context, turn = turn_for('解释自变量')
        self.assertEqual(ontology.build(turn, context)['learner_state']['attempt']['value'], 'none')

    def test_skip_signal_closes_turn(self):
        context, turn = turn_for('这题先不做了', tutoring=PENDING)
        turn = annotate(turn, 'engagement', 'skip', '先不做了')
        stage = ontology.build(turn, context)['teaching_stage']
        self.assertEqual(stage['turn_state'], 'closing')
        self.assertEqual(stage['next'], 'close')

    def test_answer_seeking_without_disclosure_closes_turn(self):
        context, turn = turn_for('解释信度，不要给我完整答案')
        turn = annotate(turn, 'engagement', 'answer_seeking', '不要给我完整答案')
        stage = ontology.build(turn, context)['teaching_stage']
        self.assertEqual(stage['turn_state'], 'closing')

    def test_missing_affect_and_history_stay_null(self):
        context, turn = turn_for('解释自变量')
        state = ontology.build(turn, context)['learner_state']
        self.assertIsNone(state['affect']['value'])
        self.assertIsNone(state['history']['value'])

    def test_unknown_label_is_rejected(self):
        self.assertFalse(ontology.valid_label('intent', 'explain'))
        self.assertFalse(ontology.valid_label('difficulty_locus', 'bored'))
        self.assertTrue(ontology.valid_label('difficulty_locus', 'discrimination'))

    def test_final_summary_carries_view_without_touching_existing_keys(self):
        context, turn = turn_for('解释自变量')
        summary = final_summary(context, {'answer_status': 'answered', 'reply': ''})
        for key in ('schema_version', 'parser', 'model_calls', 'actions', 'states', 'resolution_status'):
            self.assertIn(key, summary)
        self.assertEqual(summary['six_dim']['request_intent']['primary'], 'knowledge_query')
        json.dumps(summary)


if __name__ == '__main__':
    unittest.main()
