import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from agents.context_sufficiency import EvidenceDecision
from agents.conversation_router import RoutingResult
from agents.evidence_extractor import AnalysisResult
from agents.quality_checker import QualityResult, QualityChecker
from agents.response_generator import requests_supplementary_proof
from agents.strategy_router import InstructionalMove
from agents.teaching_planner import TeachingPlan
from models.student_state import StudentState
from models.learner_profile import LearnerProfile
from models.lesson_plan import LessonPlan, LessonStep
from knowledge.textbook import TextbookChunk
from orchestrator import TutorOrchestrator

class QualityGuardTests(unittest.TestCase):
    def tutor(self, qualities):
        tutor=TutorOrchestrator.__new__(TutorOrchestrator)
        for name in ('memory','conversation_router','context_sufficiency','lesson_planner','evidence_extractor','state_analyzer','teaching_planner','strategy_router','question_designer','response_generator','quality_checker','state_updater','tutor_error_detector'):
            setattr(tutor,name,Mock())
        tutor.textbook_chunks=[]
        tutor.memory.read_version.return_value=('mock-version',0)
        tutor.memory.get_history.return_value=[]
        tutor.memory.retrieve_context.return_value={'summary':'暂无相关学习记录','retrieval':{}}
        tutor.memory.get_active_goal.return_value='旧目标'
        tutor.memory.get_recent_moves.return_value=[]
        tutor.memory.get_misconceptions.return_value=[]
        tutor.memory.commit_learning_turn.return_value={'status':'committed','event_id':'mock-turn'}
        state=StudentState(student_id='guard-test',current_concept='旧目标',mastery=.6)
        tutor.memory.get_state.return_value=state
        tutor.memory.get_profile.return_value=LearnerProfile()
        tutor.memory.get_lesson_plan.return_value=LessonPlan(goal='新目标',steps=[LessonStep(step_id='S1',objective='目标')],current_step='S1')
        tutor.conversation_router.route.return_value=RoutingResult(intent='switch_topic',topic='新目标',confidence=1,student_move='question')
        tutor.context_sufficiency.check.return_value=EvidenceDecision(status='sufficient',source_ids=['1'],reason='条件完整')
        tutor.evidence_extractor.analyze.return_value=AnalysisResult()
        tutor.state_analyzer.build.return_value=state.model_copy(deep=True)
        tutor.teaching_planner.plan.return_value=TeachingPlan(goal='新目标',strategy='worked_example',action='explain',difficulty='medium')
        tutor.strategy_router.select.return_value=InstructionalMove(instructional_move='direct_explanation',action='explain')
        tutor.response_generator.generate.side_effect=['错误草稿一','错误草稿二']
        tutor.quality_checker.check.side_effect=qualities
        tutor.state_updater.update.return_value=SimpleNamespace(state=state,new_evidence=[],new_hypotheses=[],resolve_misconceptions=False,raw={},step_completed=False,step_reason="")
        tutor.tutor_error_detector.detect.return_value=SimpleNamespace(detected=False,rollback=False,model_dump=lambda:{})
        return tutor
    def run_turn(self,tutor):
        source=TextbookChunk(source='教材.txt',section='小节',text='已知条件',terms=frozenset())
        with patch('orchestrator.retrieve_hybrid',return_value=[source]),patch('orchestrator.retrieve_figures',return_value=[]),patch('orchestrator.expand_proof_sources',return_value=([source],None)),patch('orchestrator.enrich_sources',return_value=([source],None)):
            return tutor.handle_turn('guard-test','解释这个证明')
    def test_failed_final_check_never_publishes_draft_or_advances(self):
        tutor=self.tutor([QualityResult(passed=False,issues=['与原文矛盾'])]*2)
        result=self.run_turn(tutor)
        self.assertEqual(result['answer_status'],'quality_rejected')
        self.assertFalse(result['quality']['passed'])
        self.assertNotIn('错误草稿',result['reply'])
        self.assertFalse(result['step_advanced'])
        self.assertEqual(result['student_state']['mastery'],.6)
        for key in ('textbook_sources','image_refs','pdf_image_refs','pdf_references'):
            self.assertEqual(result[key],[])
        tutor.state_updater.update.assert_not_called()
        tutor.memory.set_active_goal.assert_not_called()
        tutor.memory.push_recent_move.assert_not_called()
        tutor.memory.save_state.assert_not_called()
        tutor.memory.save_lesson_plan.assert_not_called()
        tutor.memory.update_effectiveness.assert_not_called()
        self.assertEqual(tutor.response_generator.generate.call_count,2)
        saved=' '.join(str(call) for call in tutor.memory.append.call_args_list)
        self.assertNotIn('错误草稿',saved)
    def test_successful_revision_is_the_only_published_answer(self):
        tutor=self.tutor([QualityResult(passed=False,issues=['事实错误']),QualityResult(passed=True)])
        tutor.response_generator.generate.side_effect=['错误草稿','修订后的正确讲解']
        result=self.run_turn(tutor)
        self.assertEqual(result['answer_status'],'answered')
        self.assertEqual(result['reply'],'修订后的正确讲解')
        self.assertEqual(result['regenerated'],1)
        tutor.state_updater.update.assert_called_once()
        tutor.memory.commit_learning_turn.assert_called_once()
        committed=tutor.memory.commit_learning_turn.call_args.kwargs
        self.assertEqual(committed['point'],'新目标')
        self.assertEqual(committed['reply'],'修订后的正确讲解')
        self.assertNotIn('错误草稿',committed['reply'])
        saved=' '.join(str(call) for call in tutor.memory.append.call_args_list)
        self.assertNotIn('错误草稿',saved)
    def test_contradictory_check_is_rejected_in_actual_turn(self):
        tutor=self.tutor([QualityResult(passed=True,issues=['事实错误'])]*2)
        result=self.run_turn(tutor)
        self.assertEqual(result['answer_status'],'quality_rejected')
        tutor.state_updater.update.assert_not_called()

    def test_supplementary_proof_has_room_for_all_required_conclusions(self):
        self.assertTrue(requests_supplementary_proof('解释定理（3）⇒（4）；如果教材没有写证明，请标明补充推导'))
        self.assertFalse(requests_supplementary_proof('解释这段文字'))
        self.assertFalse(requests_supplementary_proof('证明这个结论'))
        plan=TeachingPlan(goal='补充证明',strategy='worked_example',action='explain',difficulty='medium')
        self.assertEqual(QualityChecker._rule_check('推理。'*100,plan,{'supplementary_proof':True}),[])
        self.assertTrue(QualityChecker._rule_check('推理。'*100,plan,{}))

    def test_absent_quality_result_is_not_publishable(self):
        self.assertFalse(TutorOrchestrator._quality_accepted(None))
    def test_issues_override_contradictory_pass_flag(self):
        self.assertFalse(TutorOrchestrator._quality_accepted(QualityResult(passed=True,issues=['事实错误'])))
        self.assertTrue(TutorOrchestrator._quality_accepted(QualityResult(passed=True)))

if __name__=='__main__':unittest.main()
