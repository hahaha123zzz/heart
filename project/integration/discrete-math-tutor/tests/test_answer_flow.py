"""明确解释分流：核验仍执行，省去评估，保留事务和后续辅导。"""
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

from agents.quality_checker import QualityResult
from knowledge.textbook import TextbookChunk
from models.lesson_plan import LessonPlan, LessonStep
from models.task_understanding import TaskUnderstanding
from tests import test_quality_guard as fixtures


class AnswerFlowTests(unittest.TestCase):
    def tutor(self, intents=None, **routing):
        tutor = fixtures.QualityGuardTests().tutor([QualityResult(passed=True)])
        tutor.memory.get_active_goal.return_value = '随机区组设计'
        tutor.memory.get_lesson_plan.return_value = None
        tutor.memory.lesson = LessonPlan(goal='随机区组设计', steps=[LessonStep(step_id='S1', objective='分配处理')], current_step='S1')
        tutor.lesson_planner.create.return_value = tutor.memory.lesson.model_copy(deep=True)
        tutor.conversation_router.route.return_value = TaskUnderstanding(
            student_move='question', confidence=.98, learning_intents=intents or ['explain'], **routing)
        tutor.response_generator.generate.side_effect = ['已核验的讲解。[1]']
        return tutor

    def run_turn(self, tutor, message='请解释随机区组设计并引用教材'):
        source = TextbookChunk(source='教材.txt', section='随机区组设计', text='区组内随机分配处理', terms=frozenset())
        with ExitStack() as stack:
            stack.enter_context(patch('orchestrator.retrieve_course', return_value=[source]))
            stack.enter_context(patch('orchestrator.retrieve_figures', return_value=[]))
            stack.enter_context(patch('orchestrator.expand_proof_sources', return_value=([source], None)))
            stack.enter_context(patch('orchestrator.enrich_sources', return_value=([source], None)))
            stack.enter_context(patch('orchestrator.complete_pdf_references', return_value=[]))
            stack.enter_context(patch.dict('os.environ', {'VISUALIZATION_ON_DEMAND': '0', 'VISUALIZATION_ROLLOUT': 'off'}))
            return tutor.handle_turn('guard-test', message)

    def test_content_questions_skip_evaluation_but_keep_checks_and_memory(self):
        for intents in [['explain'], ['compare', 'explain'], ['example'], ['summary'], ['hint'], ['proof']]:
            with self.subTest(intents=intents):
                tutor = self.tutor(intents)
                before = tutor.memory.get_state.return_value.model_dump()
                result = self.run_turn(tutor)
                self.assertEqual(result['response_path'], 'direct_answer')
                self.assertEqual(result['answer_status'], 'answered')
                self.assertFalse(result['step_advanced'])
                self.assertIsNone(result['lesson_progress'])
                for name, method in [('lesson_planner', 'create'), ('evidence_extractor', 'analyze'),
                                     ('state_analyzer', 'build'), ('teaching_planner', 'plan'),
                                     ('strategy_router', 'select'), ('question_designer', 'design'), ('state_updater', 'update')]:
                    getattr(getattr(tutor, name), method).assert_not_called()
                tutor.context_sufficiency.check.assert_called_once()
                tutor.quality_checker.check.assert_called_once()
                tutor.memory.retrieve_context.assert_called_once()
                committed = tutor.memory.commit_learning_turn.call_args.kwargs
                self.assertIsNone(committed['lesson_plan'])
                self.assertEqual(committed['evidence'], [])
                self.assertEqual(committed['hypotheses'], [])
                self.assertFalse(committed['decision'].eligible)
                for field in ['mastery', 'confidence', 'metacognition', 'steps_mastery']:
                    self.assertEqual(result['student_state'][field], before[field])
                self.assertEqual(result['teaching_plan']['action'], 'give_hint' if intents == ['hint'] else
                                 'give_example' if intents == ['example'] else 'summarize' if intents == ['summary'] else 'explain')

    def test_existing_course_plan_is_not_replaced_or_advanced(self):
        tutor = self.tutor()
        plan = tutor.memory.lesson
        tutor.memory.get_lesson_plan.return_value = plan
        before = plan.model_dump()
        self.run_turn(tutor)
        self.assertEqual(plan.model_dump(), before)
        self.assertIsNone(tutor.memory.commit_learning_turn.call_args.kwargs['lesson_plan'])

    def test_attempt_practice_check_and_uncertain_question_keep_tutoring(self):
        cases = [('attempt', ['explain'], .98), ('question', ['practice'], .98),
                 ('question', ['check_answer'], .98), ('question', ['explain'], .6), ('question', [], .98)]
        for move, intents, confidence in cases:
            with self.subTest(move=move, intents=intents, confidence=confidence):
                tutor = self.tutor()
                tutor.conversation_router.route.return_value = TaskUnderstanding(
                    student_move=move, confidence=confidence, learning_intents=intents)
                result = self.run_turn(tutor)
                self.assertEqual(result['response_path'], 'tutoring')
                tutor.evidence_extractor.analyze.assert_called_once()
                tutor.teaching_planner.plan.assert_called_once()
                tutor.strategy_router.select.assert_called_once()
                tutor.state_updater.update.assert_called_once()

    def test_stepwise_learning_keeps_course_planning(self):
        tutor = self.tutor()
        result = self.run_turn(tutor, '带我一步步学习随机区组设计')
        self.assertEqual(result['response_path'], 'tutoring')
        tutor.lesson_planner.create.assert_called_once()

    def test_rejected_draft_is_not_committed_as_a_success(self):
        tutor = self.tutor()
        tutor.response_generator.generate.side_effect = ['错误草稿', '仍然错误']
        tutor.quality_checker.check.side_effect = [QualityResult(passed=False, issues=['内容错误'])] * 2
        result = self.run_turn(tutor)
        self.assertEqual(result['answer_status'], 'quality_rejected')
        self.assertNotIn('草稿', result['reply'])
        tutor.memory.commit_learning_turn.assert_not_called()
        tutor.state_updater.update.assert_not_called()

    def test_deleted_memory_still_stops_publication(self):
        tutor = self.tutor()
        tutor.memory.repo.memory_epoch.return_value = 1
        result = self.run_turn(tutor)
        self.assertEqual(result['answer_status'], 'memory_deleted')
        tutor.response_generator.generate.assert_not_called()
        tutor.memory.commit_learning_turn.assert_not_called()

    def test_follow_up_uses_history_and_preferences_without_reassessing_ability(self):
        tutor = self.tutor(needs_context=True)
        tutor.memory.get_history.return_value = [{'role': 'user', 'content': '上次讨论随机区组设计'}]
        tutor.memory.get_profile.return_value.preferences = {'answer_length': .8}
        tutor.memory.retrieve_context.return_value = {'summary': '喜欢做饭例子', 'retrieval': {}}
        self.run_turn(tutor, '为什么这样能减少个体差异？')
        arguments = tutor.response_generator.generate.call_args
        self.assertEqual(arguments.args[3], tutor.memory.get_history.return_value)
        self.assertEqual(arguments.kwargs['learner_preferences'], {'answer_length': .8})
        self.assertIn('做饭', arguments.kwargs['memory_context']['summary'])
        tutor.state_updater.update.assert_not_called()

    def test_deleted_during_generation_does_not_publish_saved_reply(self):
        tutor = self.tutor()
        tutor.memory.commit_learning_turn.return_value = {'status': 'forgotten'}
        result = self.run_turn(tutor)
        self.assertEqual(result['answer_status'], 'memory_deleted')
        self.assertNotIn('已核验的讲解', result['reply'])
        self.assertEqual(result['textbook_sources'], [])

    def test_concurrent_state_is_preserved_by_existing_commit_result(self):
        tutor = self.tutor()
        tutor.memory.commit_learning_turn.return_value = {'status': 'conflict'}
        result = self.run_turn(tutor)
        self.assertFalse(result['step_advanced'])
        self.assertIn('未覆盖新状态', result['step_reason'])


if __name__ == '__main__':
    unittest.main()
