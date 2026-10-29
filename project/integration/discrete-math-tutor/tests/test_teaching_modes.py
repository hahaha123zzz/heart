"""本轮教法优先、无额外规划调用及待答题保护。"""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from agents.adaptive_tutoring import analyze_teaching_turn
from agents.agent_loop_service import _publish_gate, run_agent_loop_turn
from agents.agent_loop import LoopResult
from agents.q3_navigation import LearningTarget, SourceRef, StubLearningNavigator
from agents.task_execution import build_execution
from agents.teaching_planner import TeachingPlan
from agents.teaching_policy import resolve_teaching_mode, teaching_mode_instructions
from models.chat_request import ChatRequest
from models.task_context import TaskContext, TaskObject
from models.task_understanding import TaskUnderstanding
from agents.task_context_builder import TaskContextBuilder
from tests.test_adaptive_tutoring import prior, record, turn
from tests.test_q3_q4_integration import FakeMemory, ScriptedLLM, tool_round
from llm.client import ChatToolResult


class TeachingModeTests(unittest.TestCase):
    def test_natural_style_is_turn_local_and_overrides_saved_style(self):
        builder = TaskContextBuilder()
        saved = {'question_frequency': 1., 'example_density': 0.}
        context = builder.build(student_id='s', message='这次少提问，多举例', preferences=saved)
        self.assertEqual(context.preferences, {'question_frequency': 0., 'example_density': 1.})
        self.assertEqual(saved, {'question_frequency': 1., 'example_density': 0.})
        self.assertEqual(builder.build(student_id='s', message='继续', preferences=saved).preferences, saved)
        self.assertEqual(builder.build(student_id='s', message='不要少提问', preferences=saved).preferences, saved)
        self.assertEqual(builder.build(student_id='s', message='不只举例', preferences=saved).preferences, saved)

    def test_only_example_preserves_pending_without_new_check_or_grading(self):
        old = prior(pending=True)
        for message in ('只给我举例', '只要例子', '只想看例子', '只讲例子', '只讲一个例子'):
            with self.subTest(message=message):
                model = Mock()
                context = TaskContextBuilder().build(student_id='s', message=message,
                                                     preferences={'question_frequency': 1.})
                t = turn(message, old, model, preferences=context.preferences)
                model.chat_json.assert_not_called()
                self.assertEqual(t.progress.pending_question.model_dump(), old['progress']['pending_question'])
                self.assertFalse(t.strategy_decision.invite_check)
                self.assertFalse(record(t, check_prompt='再考一题？', check_focus='操纵').success)
                self.assertTrue(turn('继续', t.state).state['allow_check'])

    def test_explicit_modes_and_negations(self):
        cases = {
            '直接解释自变量': 'direct',
            '查看完整解答': 'direct',
            '不要再引导，完整解释': 'direct',
            '不要直接告诉我答案，带我思考': 'guided',
            '只给提示': 'guided',
            '不要引导我，直接讲解': 'direct',
            '不要考考我': 'auto',
            '不想考前复习': 'auto',
            '考考我': 'practice',
            '给我一道练习题': 'practice',
            '帮我复习信度和效度': 'review',
            '先考考我，算了直接解释': 'direct',
            '直接讲解之后，还是带我思考吧': 'guided',
            '下一步': 'auto',
            '我懂了': 'auto',
            '这个变量影响什么': 'auto',
        }
        for message, expected in cases.items():
            with self.subTest(message=message):
                self.assertEqual(resolve_teaching_mode(message), expected)

    def test_direct_request_overrides_probe_preferences_without_new_assessment(self):
        model = Mock()
        old = prior(pending=True)
        question = old['progress']['pending_question']
        t = turn('直接解释这个例子', old, model,
                 preferences={'question_frequency': 1., 'teaching_sequence': 0.})
        model.chat_json.assert_not_called()
        self.assertEqual(t.strategy, 'explain')
        self.assertFalse(t.strategy_decision.invite_check)
        self.assertTrue(t.state['allow_check'])  # 本轮禁出检查不改持久偏好。
        self.assertIsNone(t.state['assessment'])
        self.assertEqual(t.progress.pending_question.model_dump(), question)
        self.assertFalse(record(t, check_prompt='新问题？', check_focus='操纵').success)
        self.assertEqual(t.public()['teaching_mode'], 'direct')

    def test_mode_is_turn_local_and_does_not_change_mastery(self):
        t = turn('直接解释自变量', preferences={'question_frequency': 1.})
        record(t)
        resumed = turn('继续', t.state)
        self.assertEqual(resumed.teaching_mode, 'auto')
        self.assertTrue(resumed.state['allow_check'])
        self.assertFalse(resumed.state['formal_mastery'])

    def test_guidance_practice_and_review_are_not_answers_to_pending_question(self):
        for message in ('带我思考', '只给提示', '考考我', '帮我复习'):
            with self.subTest(message=message):
                model = Mock()
                old = prior(pending=True)
                t = turn(message, old, model)
                model.chat_json.assert_not_called()
                self.assertEqual(t.progress.pending_question.model_dump(), old['progress']['pending_question'])
                self.assertFalse(t.progress.learning_evidence)

    def test_practice_is_explicit_but_no_quiz_still_wins(self):
        decision = analyze_teaching_turn('考考我', question_frequency=0.)
        self.assertEqual(decision.strategy, 'guided_practice')
        self.assertTrue(decision.invite_check)
        self.assertFalse(analyze_teaching_turn('考考我，但不要出题').invite_check)
        t = turn('给我一道练习题', preferences={'question_frequency': 0., 'teaching_sequence': 1.})
        self.assertTrue(t.state['allow_check'])
        self.assertEqual(t.progress.learner_profile.teaching_strategy, 'probe_first')
        self.assertTrue(record(t, check_prompt='谁是自变量？', check_focus='操纵').success)

    def test_short_no_quiz_request_cannot_turn_review_into_mandatory_practice(self):
        message = '请复习自变量和因变量的关系，说明重点依据，不出题。'
        self.assertEqual(resolve_teaching_mode(message), 'review')
        self.assertFalse(analyze_teaching_turn(message, question_frequency=1.).invite_check)
        state = turn(message, preferences={'question_frequency': 1.})
        self.assertFalse(state.state['allow_check'])
        self.assertFalse(state.progress.learning_evidence)
        for negative in ('不出题', '不再出题', '不必出题', '无需出题', '不得出题'):
            with self.subTest(negative=negative):
                self.assertNotEqual(resolve_teaching_mode(negative), 'practice')
                self.assertFalse(analyze_teaching_turn(negative, question_frequency=1.).invite_check)

    def test_guidance_invites_one_step_but_hint_only_does_not_require_answer(self):
        self.assertTrue(analyze_teaching_turn('带我思考如何区分变量', question_frequency=0.).invite_check)
        for message in ('只给提示', '第2级提示', '再给一个提示', '给我一点提示'):
            self.assertFalse(analyze_teaching_turn(message, question_frequency=1.).invite_check)

    def test_explicit_textbook_request_requires_original_evidence(self):
        self.assertEqual(analyze_teaching_turn('直接解释教材中变量的区别').evidence_mode, 'textbook')

    def test_question_revision_supplies_public_canonical_prompt_without_answer_key(self):
        t = turn('回到刚才的题', prior(pending=True))
        prompt = t.progress.pending_question.prompt
        record(t, check_prompt=prompt, check_focus='操纵')
        accepted, reason = t.gate('换个问法：哪一个是自变量？')
        self.assertFalse(accepted)
        self.assertIn(prompt, reason)
        self.assertNotIn('PRIVATE-', reason)
        self.assertTrue(t.gate('先看研究者操纵的条件。\n\n' + prompt)[0])

    def test_tool_protocol_cannot_be_published_as_a_lesson(self):
        gate = _publish_gate(None, SimpleNamespace(message='关系说明'), None, teaching=SimpleNamespace(evidence_mode='blended'))
        for protocol in ('<｜DSML｜function_calls>', '<｜｜DSML｜｜ calls>',
                         '<||DSML|| calls>', '</｜｜DSML｜｜ invoke>', '<tool_call name="retrieve_course">'):
            with self.subTest(protocol=protocol):
                accepted, reason = gate('我先查教材。\n'+protocol, LoopResult())
                self.assertFalse(accepted)
                self.assertIn('内部工具协议', reason)

    def test_legacy_plan_consumes_same_mode_when_router_omits_intent(self):
        for message, mode, action in (
            ('直接解释', 'direct', 'explain'),
            ('带我思考', 'guided', 'give_hint'),
            ('考考我', 'practice', 'ask_question'),
            ('帮我复习', 'review', 'explain'),
        ):
            with self.subTest(mode=mode):
                execution = build_execution(message, TaskUnderstanding())
                plan = TeachingPlan(goal='理解', strategy='socratic_questioning',
                                    action='ask_question', difficulty='medium')
                execution.align(plan)
                self.assertEqual(plan.action, action)
                self.assertEqual(execution.teaching_mode, mode)
                self.assertIn(teaching_mode_instructions(mode), execution.instructions())

    def test_review_does_not_claim_exam_weight_or_mastery(self):
        instructions = teaching_mode_instructions('review')
        self.assertIn('不从图谱中心性推断考试分值', instructions)
        self.assertIn('不强制测试', instructions)

    def test_importance_and_relationship_provenance_in_both_answer_paths(self):
        from agents.course_prompts import RESPONSE
        from agents.loop_prompts import build_loop_system_prompt
        for prompt in (RESPONSE, build_loop_system_prompt(target=None, definitions=[])):
            self.assertIn('没有考纲或教师依据不得声称考试重点或分值', prompt)
            self.assertIn('推断的联系注明是教学分析', prompt)

    def test_direct_mode_can_skip_legacy_planner_even_when_router_omits_intent(self):
        execution = build_execution('直接解释', TaskUnderstanding())
        self.assertTrue(execution.can_answer_directly(
            TaskUnderstanding(student_move='question', confidence=.9), '直接解释'))

    def test_current_request_overrides_old_mode_in_saved_state(self):
        old = prior()
        old['teaching_mode'] = 'guided'
        t = turn('直接解释', old)
        self.assertEqual(t.public()['teaching_mode'], 'direct')
        self.assertIn('本轮直接讲解', t.instructions())

    def test_direct_request_replaces_inherited_hint_from_router(self):
        execution = build_execution('直接解释这个概念', TaskUnderstanding(
            learning_intents=['hint'], answer_constraints=['hint_only', 'no_full_answer']))
        self.assertFalse(execution.hint_only)
        self.assertIn('explain', execution.learning_intents)

    def test_validated_hint_scope_cannot_be_expanded_by_direct_mode(self):
        context = TaskContext(student_id='s', message='直接解释',
                              graph_snapshot={'answer_scope': 'hint', 'artifact_id': 'g'},
                              objects=[TaskObject(id='visualization:g', kind='visualization',
                                                  title='当前图', chapter_id=1, section_id=1)])
        execution = build_execution('直接解释', TaskUnderstanding(), context)
        self.assertTrue(execution.hint_only)
        plan = TeachingPlan(goal='理解', strategy='worked_example', action='explain', difficulty='medium')
        execution.align(plan)
        self.assertEqual(plan.action, 'give_hint')


class TeachingModeHostTests(unittest.TestCase):
    @patch.dict('os.environ', {'ADAPTIVE_TUTORING_ENABLED': '1', 'Q5_LEARNING_ENABLED': '0'})
    def test_course_review_requires_retrieval_without_a_new_question(self):
        model = ScriptedLLM([tool_round('retrieve_course', {'query': '自变量 因变量 关系', 'limit': 1}),
            ChatToolResult(text='教材区分操纵的条件与测量的反应。[1]', finish_reason='stop')])
        message = '请复习自变量和因变量的关系，不出题。'
        context = TaskContext(student_id='s', session_id='x', message=message, knowledge_point='自变量')
        navigator = StubLearningNavigator(target=LearningTarget(target_id='p', name='自变量'),
            sources=[SourceRef('e1', 'd', '自变量是研究者操纵的变量。', version='v')])
        with patch('agents.tools.first_wave_runtime.bind_resources', return_value=(None, ())):
            result = run_agent_loop_turn(orchestrator=SimpleNamespace(llm=model, memory=FakeMemory(), quality_checker=None),
                request=ChatRequest(student_id='s', session_id='x', request_id='review', message=message),
                context=context, navigator=navigator, publish_gate=lambda *_: (True, ''))
        self.assertEqual(result['answer_status'], 'answered')
        self.assertEqual(model.calls[0]['tool_choice'], 'required')
        self.assertIn('retrieve_course', [t['function']['name'] for t in model.calls[0]['tools']])
        self.assertIsNone(result['teaching']['pending_check'])
        self.assertFalse(result['teaching']['formal_mastery'])

    @patch.dict('os.environ', {'ADAPTIVE_TUTORING_ENABLED': '1', 'Q5_LEARNING_ENABLED': '0'})
    def test_first_guided_question_reads_evidence_before_it_can_finish(self):
        model = ScriptedLLM([
            tool_round('retrieve_course', {'query': '自变量', 'limit': 1}),
            tool_round('teaching_step', {'strategy': 'hint', 'summary': '先辨认操纵条件',
                'check_prompt': '研究者操纵的是什么？', 'check_focus': '操纵'}),
            ChatToolResult(text='看研究者改变的条件。[1]\n研究者操纵的是什么？', finish_reason='stop')])
        message = '带我思考如何区分变量'
        request = ChatRequest(student_id='s', session_id='x', request_id='first-guide', message=message)
        context = TaskContext(student_id='s', session_id='x', message=message, knowledge_point='自变量')
        navigator = StubLearningNavigator(target=LearningTarget(target_id='p', name='自变量'),
            sources=[SourceRef('e1', 'd', '自变量是研究者操纵的变量。', version='v')])
        with patch('agents.tools.first_wave_runtime.bind_resources', return_value=(None, ())):
            result = run_agent_loop_turn(
                orchestrator=SimpleNamespace(llm=model, memory=FakeMemory(), quality_checker=None),
                request=request, context=context, navigator=navigator, publish_gate=lambda *_: (True, ''))
        self.assertEqual(result['answer_status'], 'answered')
        self.assertEqual(model.calls[0]['tool_choice'], 'required')
        self.assertTrue(model.calls[1]['tools'])
        self.assertEqual([tool['function']['name'] for tool in model.calls[1]['tools']], ['teaching_step'])
        self.assertEqual(model.calls[1]['tool_choice'], 'required')
        self.assertFalse(model.calls[2]['tools'])
        self.assertTrue(context.tutoring['pending_sources'])

    @patch.dict('os.environ', {'ADAPTIVE_TUTORING_ENABLED': '1', 'Q5_LEARNING_ENABLED': '0'})
    def test_guided_turn_keeps_tool_available_until_question_is_registered(self):
        model = ScriptedLLM([
            tool_round('teaching_step', {'strategy': 'hint', 'summary': '辨认操纵的条件',
                'check_prompt': '研究者操纵的是什么？', 'check_focus': '操纵'}),
            ChatToolResult(text='先看主动改变的条件。研究者操纵的是什么？', finish_reason='stop')])
        message = '带我思考怎么区分变量'
        context = TaskContext(student_id='s', session_id='x', message=message,
                              knowledge_point='自变量', tutoring=prior())
        request = ChatRequest(student_id='s', session_id='x', request_id='guided', message=message)
        with patch('agents.tools.first_wave_runtime.bind_resources', return_value=(None, ())), \
             patch('agents.adaptive_tutoring.verified_sources', side_effect=lambda sources: sources):
            result = run_agent_loop_turn(
                orchestrator=SimpleNamespace(llm=model, memory=FakeMemory(), quality_checker=None),
                request=request, context=context,
                navigator=StubLearningNavigator(target=LearningTarget(target_id='p', name='自变量')),
                publish_gate=lambda *_: (True, ''))
        self.assertIn('teaching_step', [tool['function']['name'] for tool in model.calls[0]['tools']])
        self.assertFalse(model.calls[1]['tools'])
        self.assertEqual(result['answer_status'], 'answered')
        self.assertEqual(result['teaching']['pending_check']['prompt'], '研究者操纵的是什么？')
        self.assertTrue(result['sources'])

    @patch.dict('os.environ', {'ADAPTIVE_TUTORING_ENABLED': '0', 'Q5_LEARNING_ENABLED': '0'})
    def test_normal_host_turn_consumes_preferences_and_mode_without_extra_llm_call(self):
        model = ScriptedLLM([ChatToolResult(text='自变量是研究者操纵的变量。', finish_reason='stop')])
        message = '直接解释自变量'
        context = TaskContext(student_id='s', session_id='x', message=message,
                              knowledge_point='自变量', preferences={'example_density': 1.})
        request = ChatRequest(student_id='s', session_id='x', request_id='mode', message=message)
        with patch('agents.tools.first_wave_runtime.bind_resources', return_value=(None, ())):
            run_agent_loop_turn(
                orchestrator=SimpleNamespace(llm=model, memory=FakeMemory(), quality_checker=None),
                request=request, context=context,
                navigator=StubLearningNavigator(target=LearningTarget(target_id='p', name='自变量')),
                publish_gate=lambda *_: (True, ''))
        self.assertEqual(len(model.calls), 1)
        prompt = model.calls[0]['messages'][0]['content']
        self.assertIn('本轮直接讲解', prompt)
        self.assertIn('多用相关辅助例子', prompt)
        self.assertNotIn('检查题并停止', prompt)


if __name__ == '__main__':
    unittest.main()
