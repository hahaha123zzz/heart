"""策略观察与规则反思：隔离 SQLite，无外部模型调用。"""
import unittest
from unittest.mock import patch
from sqlalchemy import select
from tests import test_memory_events as fixtures
from database.database import session_scope
from database.models import StrategyObservationRow, LearningEventRow
from memory.memory_manager import MemoryManager
from memory.evidence_policy import EvidenceDecision
from models.evidence import Evidence
from models.student_state import StudentState


class StrategyMemoryTests(unittest.TestCase):
    setUp=fixtures.MemoryEventTests.setUp
    tearDown=fixtures.MemoryEventTests.tearDown
    args=fixtures.MemoryEventTests.args
    count=fixtures.MemoryEventTests.count
    make_tutor=fixtures.MemoryEventTests.make_tutor
    turn=fixtures.MemoryEventTests.turn

    def commit(self, mastery=None, move="retrieval_practice", **changes):
        args=self.args()
        before=self.memory.get_state("s",self.point)
        args.update(state=before.model_copy(update={"mastery":before.mastery if mastery is None else mastery}),
            instructional_move=move,teaching_context={"strategy":"socratic_questioning","difficulty":"medium","hint_level":1})
        args.update(changes)
        result=self.memory.commit_learning_turn(**args)
        return args,result

    def observations(self):
        return self.memory.repo.strategy_observations("s",self.point)

    def test_observation_attributes_previous_move_not_current(self):
        teacher,_=self.commit(move="socratic_questioning")
        current,_=self.commit(.7,move="transfer",success=True)
        row=self.observations()[-1]
        self.assertEqual(row["teaching_event_id"],teacher["event_id"])
        self.assertEqual(row["observation_event_id"],current["event_id"])
        self.assertEqual(row["instructional_move"],"socratic_questioning")
        self.assertEqual(row["outcome"],"progress")
        self.assertIsNotNone(row["evidence_id"])
        self.assertEqual(self.memory.get_profile("s").teaching_effectiveness,{})

    def test_first_turn_and_unmeasured_attempt_are_unknown(self):
        self.commit(.6)
        self.assertEqual(self.observations()[0]["outcome"],"unknown")
        self.commit(.6)
        self.assertEqual(self.observations()[-1]["outcome"],"unknown")
        self.assertEqual(self.memory.get_profile("s",point=self.point).teaching_effectiveness,{})

    def test_question_assistance_and_missing_original_quote_do_not_measure(self):
        self.commit()
        for changes in (dict(decision=EvidenceDecision(False,False,"提问")),
                        dict(decision=EvidenceDecision(False,False,"提示后作答")),
                        dict(evidence=[Evidence(content="模型判断",source_quote="非学生原文")])):
            self.commit(.9,**changes)
            self.assertEqual(self.observations()[-1]["outcome"],"unknown")

    def test_regression_is_observed_but_small_change_is_unknown(self):
        self.commit(.8);self.commit(.5)
        self.assertEqual(self.observations()[-1]["outcome"],"regression")
        self.commit(.52)
        self.assertEqual(self.observations()[-1]["outcome"],"unknown")

    def test_duplicate_commit_does_not_duplicate_observation(self):
        args,_=self.commit()
        self.assertEqual(self.memory.commit_learning_turn(**args)["status"],"duplicate")
        self.assertEqual(self.count(StrategyObservationRow),1)

    def test_three_measurements_supply_only_weak_contextual_weight(self):
        self.commit(.2)
        for value in (.3,.4):
            self.commit(value)
        self.assertEqual(self.memory.get_profile("s",point=self.point).teaching_effectiveness,{})
        self.commit(.5)
        self.assertEqual(self.memory.get_profile("s",point=self.point).teaching_effectiveness,{"retrieval_practice":.6})
        for kwargs in ({"point":"关系"},{"point":self.point,"difficulty":"hard"},{"point":self.point,"hint_level":3}):
            self.assertEqual(self.memory.get_profile("s",**kwargs).teaching_effectiveness,{})
        self.memory.ensure_student("other")
        self.assertEqual(self.memory.get_profile("other",point=self.point).teaching_effectiveness,{})
        self.commit(.5,decision=EvidenceDecision(False,False,"未测量"))
        summary=self.memory.strategy_summary("s",self.point)[0]
        self.assertEqual(summary["measured"],3)
        self.assertEqual(summary["unknown"],1)
        self.assertTrue(summary["source_event_ids"])

    def test_invalidated_source_stops_contributing(self):
        args,_=self.commit(.2)
        for value in (.3,.4,.5):
            self.commit(value)
        with session_scope() as session:
            session.get(LearningEventRow,args["event_id"]).status="rolled_back"
        self.assertEqual(self.memory.get_profile("s",point=self.point).teaching_effectiveness,{})

    def test_history_interruption_and_point_change_stop_attribution(self):
        self.commit()
        self.memory.append_exchange("s","请解释选区","解释",{"page":4,"section_title":self.point})
        self.commit(.9)
        self.assertIsNone(self.observations()[-1]["teaching_event_id"])
        self.commit(.9)
        original=self.point
        self.point="关系"
        self.memory.save_state("s",self.point,StudentState(student_id="s",current_concept=self.point))
        self.commit(.8)
        self.assertIsNone(self.observations()[-1]["teaching_event_id"])
        self.assertEqual(self.memory.repo.strategy_observations("other",original),[])

    def test_restart_restores_committed_moves_and_ignores_error_turn(self):
        self.commit(move="transfer");self.commit(move="retrieval_practice")
        self.commit(move="hint",tutor_error="不可靠")
        restarted=MemoryManager()
        self.assertEqual(restarted.get_recent_moves("s"),["transfer","retrieval_practice"])

    def test_atomic_failure_rolls_back_observation_and_state(self):
        self.commit(.5);token=self.memory.get_version("s",self.point)
        with patch.object(self.memory.repo,"add_revision",side_effect=RuntimeError("提交失败")):
            with self.assertRaises(RuntimeError):
                self.commit(.8)
        self.assertEqual(self.count(StrategyObservationRow),1)
        self.assertEqual(self.memory.get_state("s",self.point).mastery,.5)
        self.assertEqual(self.memory.get_version("s",self.point),token)

    def test_tutor_error_and_version_conflict_skip_observation(self):
        self.commit()
        self.commit(.9,tutor_error="错误讲解")
        self.commit(.9,expected_token="过期版本")
        self.assertEqual(self.count(StrategyObservationRow),1)

    def test_legacy_profile_preserved_but_not_used_for_contextual_decisions(self):
        profile=self.memory.get_profile("s");profile.teaching_effectiveness={"worked_example":1}
        self.memory.save_profile(profile)
        self.assertEqual(self.memory.get_profile("s").teaching_effectiveness,{"worked_example":1})
        self.assertEqual(self.memory.get_profile("s",point=self.point).teaching_effectiveness,{})
        self.commit(.8,success=True)
        self.assertEqual(self.memory.get_profile("s").teaching_effectiveness,{"worked_example":1})

    def test_reflection_in_context_budget_and_delete_cascades(self):
        self.commit(.2);self.commit(.4)
        with patch("memory.retrieval._model",return_value=(None,None)):
            context=self.memory.retrieve_context("s",title=self.point,question="集合元素",budget=6000)
        self.assertTrue(context["strategy_memory"])
        self.assertIn("不能据此证明",context["strategy_memory"][0]["observations"][0]["reflection"])
        self.memory.reset("s")
        self.assertEqual(self.count(StrategyObservationRow),0)
        self.assertEqual(self.memory.strategy_summary("s",self.point),[])

    def test_legacy_event_without_conditions_is_not_measured(self):
        self.commit(.2,teaching_context={})
        self.commit(.5)
        self.assertEqual(self.observations()[-1]["outcome"],"unknown")

    def test_real_router_receives_same_condition_weight(self):
        self.commit(.2)
        for value in (.3,.4,.5):
            self.commit(value)
        tutor=self.make_tutor("attempt")
        self.turn(tutor)
        profile=tutor.strategy_router.select.call_args.args[4]
        self.assertEqual(profile.teaching_effectiveness,{"retrieval_practice":.6})

    def test_quality_rejection_does_not_create_observation(self):
        tutor=self.make_tutor("attempt",accepted=False)
        self.assertEqual(self.turn(tutor)["answer_status"],"quality_rejected")
        self.assertEqual(self.count(StrategyObservationRow),0)

    def test_real_orchestrator_persists_teaching_conditions(self):
        tutor=self.make_tutor("attempt")
        result=self.turn(tutor)
        event=self.memory.repo.get_event("s","turn:"+result["memory_commit"]["event_id"])
        self.assertEqual(event["payload"]["teaching_context"]["difficulty"],"medium")
        self.assertEqual(event["payload"]["teaching_context"]["hint_level"],1)
        self.assertEqual(self.count(StrategyObservationRow),1)
        self.assertEqual(self.observations()[0]["outcome"],"unknown")


if __name__=="__main__":
    unittest.main()
