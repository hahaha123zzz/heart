"""展示协议、正文边界及原对话保存链路。"""
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from agents.agent_loop_service import run_agent_loop_turn
from agents.learning_cards import build_learning_cards, presentation_arguments, presentation_text, published_reference_map
from agents.q3_navigation import LearningTarget, StubLearningNavigator
from llm.client import ChatToolResult
from models.chat_request import ChatRequest
from models.task_context import TaskContext
from tests.test_adaptive_tutoring import SOURCE, prior, record, turn
from tests.test_q3_q4_integration import FakeMemory, ScriptedLLM, tool_round

STEPS = [{'title': '看操纵', 'body': '找到研究者主动改变的条件。', 'source_indices': []},
         {'title': '看测量', 'body': '找到研究者观察测量的反应。', 'source_indices': []}]


class LearningCardTests(unittest.TestCase):
    def test_presentation_is_bounded_closed_schema_and_cannot_include_question(self):
        for payload in (
            {'card_kind': 'script', 'explanation_steps': STEPS},
            {'card_kind': 'step_reveal', 'explanation_steps': STEPS[:1]},
            {'card_kind': 'step_reveal', 'explanation_steps': [dict(STEPS[0], script='alert(1)'), STEPS[1]]},
            {'card_kind': 'step_reveal', 'explanation_steps': STEPS, 'comparison_labels': ['甲', '乙']},
            {'explanation_steps': STEPS},
        ):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                presentation_arguments(payload)
        t = turn('分步展开')
        self.assertFalse(record(t, card_kind='step_reveal', explanation_steps=STEPS,
                                check_prompt='新题？', check_focus='条件').success)
        self.assertIsNone(t.progress.pending_question)

    def test_card_only_repeats_published_content_and_cited_sources(self):
        t = turn('分步展开')
        self.assertTrue(record(t, card_kind='step_reveal', explanation_steps=STEPS).success)
        answer = '\n'.join(step['body'] for step in STEPS)
        cards = build_learning_cards(t, [SOURCE], answer)
        self.assertEqual([card['kind'] for card in cards], ['step_reveal', 'learning_progress'])
        self.assertEqual(cards, build_learning_cards(t, [SOURCE], answer))
        self.assertEqual(len(build_learning_cards(t, [SOURCE], '没有提及这些步骤的讲解。')), 1)
        t.state['presentation']['steps'][0]['source_indices'] = [1]
        self.assertEqual(len(build_learning_cards(t, [SOURCE], answer)), 1)
        self.assertEqual(len(build_learning_cards(t, [SOURCE], answer + '[1]')), 2)
        t.state['presentation']['steps'][0]['source_indices'] = [99]
        self.assertEqual(len(build_learning_cards(t, [SOURCE], answer + '[1]')), 1)

    def test_structured_reply_uses_same_text_and_single_number_citations(self):
        value = presentation_arguments({'card_kind': 'concept_comparison', 'comparison_labels': ['甲', '乙'],
            'comparison_rows': [{'aspect': '方法', 'left': '操纵[1]', 'right': '测量[2]', 'source_indices': [1, 2]}]})
        reply = presentation_text(value)
        self.assertIn('操纵', reply)
        self.assertIn('测量[1][2]', reply)
        self.assertNotIn('[1, 2]', reply)

    def test_published_citation_renumbering_keeps_card_bound_to_same_evidence(self):
        t = turn('分步展开')
        steps = [dict(step, source_indices=[7]) for step in STEPS]
        self.assertTrue(record(t, card_kind='step_reveal', explanation_steps=steps).success)
        source = dict(SOURCE, index=7)
        source['location'] = {'evidence': {'evidence_id': 'stable-evidence'}}
        refs = [{'source_index': 0, 'evidence': {'evidence_id': 'stable-evidence'}}]
        mapping = published_reference_map([source], refs)
        cards = build_learning_cards(t, [source], '\n'.join(step['body'] for step in STEPS)+'[1]', reference_map=mapping)
        self.assertEqual(cards[0]['steps'][0]['source_indices'], [1])
        self.assertEqual(t.state['presentation']['steps'][0]['source_indices'], [7])

    def test_comparison_keeps_labels_and_has_no_executable_actions(self):
        t = turn('给我概念对比卡')
        self.assertTrue(record(t, card_kind='concept_comparison', comparison_labels=['自变量', '因变量'],
            comparison_rows=[{'aspect': '判断方法', 'left': '主动操纵的条件', 'right': '观察测量的反应', 'source_indices': [1]}]).success)
        cards = build_learning_cards(t, [SOURCE], '自变量是主动操纵的条件；因变量是观察测量的反应。[1]')
        self.assertEqual(cards[0]['labels'], ['自变量', '因变量'])
        self.assertNotIn('actions', cards[0])

    def test_progress_never_labels_self_report_or_assisted_check_as_mastery(self):
        t = turn('我懂了', prior(pending=True))
        cards = build_learning_cards(t, [SOURCE], '可以继续。')
        progress = cards[-1]
        self.assertTrue(progress['pending'])
        self.assertFalse(progress['mastered'])
        self.assertEqual(progress['formative_attempts'], 0)
        self.assertNotIn('confidence', progress)
        self.assertNotIn('PRIVATE-', json.dumps(cards))

    def test_card_ids_are_scoped_to_student_and_session_and_greeting_has_none(self):
        t = turn('请解释')
        first = build_learning_cards(t, [], '讲解内容。')[0]['card_id']
        t.request.session_id = 'another-tab'
        self.assertNotEqual(first, build_learning_cards(t, [], '讲解内容。')[0]['card_id'])
        t.request.message = '你好'
        self.assertEqual(build_learning_cards(t, [], '你好，很高兴见到你。'), [])


class CardHostTests(unittest.TestCase):
    @patch.dict('os.environ', {'ADAPTIVE_TUTORING_ENABLED': '1', 'Q5_LEARNING_ENABLED': '0'})
    def test_requested_steps_are_executed_and_saved_with_original_conversation(self):
        answer = '\n\n'.join(step['body'] for step in STEPS)
        model = ScriptedLLM([
            tool_round('teaching_step', {'strategy': 'explain', 'summary': '分清操纵和测量',
                'card_kind': 'step_reveal', 'explanation_steps': STEPS}),
            ChatToolResult(text=answer, finish_reason='stop')])
        memory = FakeMemory()
        request = ChatRequest(student_id='s', session_id='x', request_id='cards', message='直接解释变量，并分步展开')
        context = TaskContext(student_id='s', session_id='x', message=request.message, knowledge_point='变量')
        with patch('agents.tools.first_wave_runtime.bind_resources', return_value=(None, ())):
            result = run_agent_loop_turn(orchestrator=SimpleNamespace(llm=model, memory=memory, quality_checker=None),
                request=request, context=context,
                navigator=StubLearningNavigator(target=LearningTarget(target_id='p', name='变量')),
                publish_gate=lambda *_: (True, ''))
        self.assertEqual(result['answer_status'], 'answered')
        self.assertEqual(result['learning_cards'][0]['kind'], 'step_reveal')
        self.assertEqual(memory.calls[0]['kwargs']['selection_ref']['learning_cards'], result['learning_cards'])
        self.assertEqual(result['learning_cards'][-1]['memory_epoch'], 0)
        self.assertEqual(len(model.calls), 1)


if __name__ == '__main__':
    unittest.main()
