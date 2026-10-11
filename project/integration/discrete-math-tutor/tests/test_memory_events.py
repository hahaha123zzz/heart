"""记忆事务隔离检查：临时 SQLite、模拟推断，不调用外部 API。"""
import unittest
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch

from sqlalchemy import create_engine, event, select, func
from sqlalchemy.orm import sessionmaker
from database import database as db
from database.models import Base, LearningEventRow, EventEvidenceRow, MemoryRevisionRow, EvidenceRow, ConversationRow
from memory.memory_manager import MemoryManager
from memory.evidence_policy import EvidenceDecision, assess_attempt, project_state
from models.evidence import Evidence
from models.student_state import StudentState
from models.lesson_plan import LessonPlan, LessonStep
from agents.evidence_extractor import MisconceptionHypothesis


class MemoryEventTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        @event.listens_for(self.engine, "connect")
        def fk(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        self.patch = patch.object(db, "SessionLocal", self.factory)
        self.patch.start()
        self.memory = MemoryManager()
        self.memory.ensure_student("s")
        self.point = "集合"
        self.before = StudentState(student_id="s", current_concept=self.point, mastery=.5, steps_mastery={"S1": .4})
        self.plan = LessonPlan(goal=self.point, steps=[LessonStep(step_id="S1", objective="辨认集合")], current_step="S1")
        self.memory.save_state("s", self.point, self.before)
        self.memory.save_lesson_plan("s", self.point, self.plan, self.before.steps_mastery)

    def tearDown(self):
        self.patch.stop()
        self.engine.dispose()

    def count(self, model):
        with self.factory() as session:
            return session.scalar(select(func.count()).select_from(model))

    def args(self):
        quote = "A包含元素1"
        evidence = Evidence(content=quote, source_quote=quote, confidence=.9)
        return dict(student_id="s", point=self.point, event_id=str(uuid4()),
            expected_token=self.memory.repo.memory_token("s", self.point), message=quote, reply="核对后的解释",
            state=self.before.model_copy(update={"mastery": .6}), lesson_plan=self.plan,
            decision=EvidenceDecision(True, True, "独立作答"), evidence=[evidence, evidence.model_copy()],
            hypotheses=[], strategy="socratic_questioning", success=None, instructional_move="retrieval_practice")

    def test_duplicate_event_and_duplicate_observation_are_idempotent(self):
        args = self.args()
        self.assertEqual(self.memory.commit_learning_turn(**args)["status"], "committed")
        self.assertEqual(self.memory.commit_learning_turn(**args)["status"], "duplicate")
        self.assertEqual(self.count(LearningEventRow), 1)
        self.assertEqual(self.count(EvidenceRow), 1)
        self.assertEqual(self.count(ConversationRow), 2)
        self.assertEqual(self.count(MemoryRevisionRow), 1)
        evidence = self.memory.list_evidence("s")[0]
        self.assertEqual(evidence["event_id"], args["event_id"])
        self.assertEqual(evidence["source_quote"], args["message"])

    def test_commit_failure_rolls_back_every_projection_and_record(self):
        args = self.args()
        token = args["expected_token"]
        with patch.object(self.memory.repo, "add_revision", side_effect=RuntimeError("故障注入")):
            with self.assertRaises(RuntimeError):
                self.memory.commit_learning_turn(**args)
        self.assertEqual(self.count(LearningEventRow), 0)
        self.assertEqual(self.count(EvidenceRow), 0)
        self.assertEqual(self.count(ConversationRow), 0)
        self.assertEqual(self.memory.repo.memory_token("s", self.point), token)

    def test_stale_version_keeps_new_state_and_records_conflict(self):
        args = self.args()
        self.memory.save_state("s", self.point, self.before.model_copy(update={"mastery": .8}))
        result = self.memory.commit_learning_turn(**args)
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(self.memory.get_state("s", self.point).mastery, .8)
        self.assertEqual(self.count(EventEvidenceRow), 0)
        self.assertEqual(self.count(ConversationRow), 2)

    def test_tutor_error_discards_candidate_changes_and_hypotheses(self):
        args = self.args()
        token = args["expected_token"]
        args["tutor_error"] = "错误讲解"
        args["success"] = False
        args["hypotheses"] = [(MisconceptionHypothesis(type="set_element_confusion", description="混淆", confidence=1), None)]
        self.assertEqual(self.memory.commit_learning_turn(**args)["status"], "rolled_back")
        self.assertEqual(self.memory.repo.memory_token("s", self.point), token)
        self.assertEqual(self.memory.get_misconceptions("s", self.point), [])
        self.assertEqual(self.memory.get_profile("s").teaching_effectiveness, {})
        self.assertEqual(self.memory.list_evidence("s")[0]["evidence_type"], "tutor_error")

    def test_same_event_hypothesis_counts_once_and_later_event_reopens(self):
        args = self.args()
        hypo = MisconceptionHypothesis(type="set_element_confusion", description="混淆集合元素", source_quote=args["message"], confidence=1)
        args["hypotheses"] = [(hypo, None), (hypo.model_copy(), None)]
        self.memory.commit_learning_turn(**args)
        item = self.memory.get_misconceptions("s", self.point)[0]
        self.assertEqual(item.evidence_count, 1)
        self.assertNotEqual(item.status, "confirmed")
        self.memory.resolve_misconceptions("s", self.point)
        next_args = self.args(); next_args["hypotheses"] = [(hypo, item.id)]
        self.memory.commit_learning_turn(**next_args)
        item = self.memory.get_misconceptions("s", self.point)[0]
        self.assertEqual(item.evidence_count, 1)
        self.assertNotEqual(item.status, "resolved")

    def test_question_preserves_mastery_steps_gap_and_unknown_effectiveness(self):
        raw = {"mastery":1, "steps_mastery":{"S1":1}, "confidence":.8}
        candidate = self.before.model_copy(update={"mastery":1, "steps_mastery":{"S1":1}})
        decision = assess_attempt(SimpleNamespace(student_move="question", confidence=1), "为什么", [])
        state = project_state(self.before, candidate, raw, decision)
        self.assertEqual(state.mastery, self.before.mastery)
        self.assertEqual(state.steps_mastery, self.before.steps_mastery)
        args=self.args();args.update(state=state, decision=decision, evidence=[])
        self.memory.commit_learning_turn(**args)
        self.assertEqual(self.memory.get_profile("s").teaching_effectiveness,{})

    def test_unattributed_or_assisted_attempt_is_not_mastery_evidence(self):
        routing = SimpleNamespace(student_move="attempt", confidence=1)
        fake = Evidence(content="学生懂了", source_quote="教材中的另一句话")
        self.assertFalse(assess_attempt(routing,"A包含1",[fake]).eligible)
        grounded=Evidence(content="A包含1",source_quote="A包含1")
        assisted={"payload":{"instructional_move":"worked_example"}}
        self.assertFalse(assess_attempt(routing,"A包含1",[grounded],assisted,True).eligible)
        self.assertFalse(assess_attempt(routing,"A包含1",[grounded],None,True).eligible)
        self.assertTrue(assess_attempt(routing,"A包含1",[grounded]).eligible)

    def test_provisional_numeric_observation_is_blended_only_once(self):
        state=project_state(self.before,self.before.model_copy(update={"mastery":.9}),
            {"mastery":.7},EvidenceDecision(True,True,"原文"))
        self.assertAlmostEqual(state.mastery,.58)
        state=project_state(self.before,self.before,{"mastery":1,"steps_mastery":{"S1":1}},EvidenceDecision(True,True,"原文"))
        self.assertLess(state.mastery,.8)
        self.assertLess(state.steps_mastery["S1"],.8)

    def test_selection_event_preserves_source_and_student_reset_cascades(self):
        reference={"document_id":"book", "page":4, "rects":[[.1,.2,.3,.4]]}
        self.memory.append("s","user","解释选区",selection_ref=reference)
        with self.factory() as session:
            row=session.scalar(select(LearningEventRow))
            self.assertEqual(row.event_type,"pdf_selection")
            self.assertEqual(row.payload["selection_ref"],reference)
        self.memory.commit_learning_turn(**self.args())
        self.memory.reset("s")
        for model in (LearningEventRow,EventEvidenceRow,MemoryRevisionRow,EvidenceRow,ConversationRow):
            self.assertEqual(self.count(model),0)

    def test_submission_idempotency_and_verification_are_separate(self):
        output={"parts":[{"part_id":"a","confirmed":True,"method":"rule","score":100},
                          {"part_id":"b","confirmed":False,"method":"ai_assisted","score":80}]}
        for _ in range(2):
            self.memory.record_exercise_submission("s",self.point,"sub1","q1","v1",{"a":"1","b":"证明"},output,True)
        evidence=self.memory.list_evidence("s")
        self.assertEqual(len(evidence),2)
        self.assertEqual({x["verification"] for x in evidence},{"rule_verified","ai_provisional"})
        self.assertFalse(any(x["independent"] for x in evidence))
        self.assertEqual(self.memory.get_state("s",self.point).mastery,.5)

    def test_legacy_records_keep_unknown_provenance(self):
        self.memory.add_evidence("s",self.point,"behavior","旧记录",.5)
        evidence=self.memory.list_evidence("s")[0]
        self.assertEqual(evidence["verification"],"legacy_unverified")
        self.assertIsNone(evidence["event_id"])
        self.assertEqual(self.memory.list_evidence("other"),[])

    def test_revision_includes_all_flushed_changes(self):
        args=self.args(); self.memory.commit_learning_turn(**args)
        with self.factory() as session:
            revision=session.scalar(select(MemoryRevisionRow))
            self.assertEqual(revision.after["knowledge_states"][0]["mastery"],.6)
            self.assertEqual(revision.after["active_state"][0]["knowledge_point"],self.point)

    def make_tutor(self, move="question", accepted=True, rollback=False):
        from unittest.mock import Mock
        from orchestrator import TutorOrchestrator
        from agents.conversation_router import RoutingResult
        from agents.evidence_extractor import AnalysisResult
        from agents.context_sufficiency import EvidenceDecision as RetrievalDecision
        from agents.quality_checker import QualityResult
        from agents.state_updater import UpdateResult
        from agents.state_analyzer import StateAnalyzer
        from agents.strategy_router import InstructionalMove
        from agents.teaching_planner import TeachingPlan
        from agents.tutor_error_detector import TutorErrorDetector
        tutor=TutorOrchestrator.__new__(TutorOrchestrator)
        tutor.memory=self.memory
        tutor.textbook_chunks=[]
        for name in ("conversation_router","context_sufficiency","lesson_planner","evidence_extractor",
                     "misconception_resolver","teaching_planner","strategy_router","question_designer",
                     "response_generator","quality_checker","state_updater"):
            setattr(tutor,name,Mock())
        tutor.state_analyzer=StateAnalyzer()
        tutor.tutor_error_detector=TutorErrorDetector()
        tutor.conversation_router.route.return_value=RoutingResult(student_move=move, confidence=1)
        tutor.context_sufficiency.check.return_value=RetrievalDecision(status="sufficient",source_ids=["1"],reason="支持")
        evidence=Evidence(content="A包含元素1",source_quote="A包含元素1",confidence=.9)
        tutor.evidence_extractor.analyze.return_value=AnalysisResult(evidence=[evidence],observation={"mastery":.7})
        tutor.teaching_planner.plan.return_value=TeachingPlan(goal=self.point,strategy="worked_example",action="explain",difficulty="medium")
        tutor.strategy_router.select.return_value=InstructionalMove(instructional_move="retrieval_practice",action="ask_question")
        tutor.response_generator.generate.return_value="教材支持的回答"
        tutor.quality_checker.check.return_value=QualityResult(passed=accepted,issues=[] if accepted else ["不可靠"])
        candidate=self.before.model_copy(update={"mastery":.9,"steps_mastery":{"S1":1},"turn_count":1})
        raw={"mastery":.7,"steps_mastery":{"S1":1},
             "tutor_error":{"detected":rollback,"rollback":rollback,"reason":"错误讲解","error_type":"wrong_explanation"}}
        tutor.state_updater.update.return_value=UpdateResult(state=candidate,raw=raw,new_evidence=[evidence],step_completed=True)
        return tutor

    def turn(self,tutor):
        from knowledge.textbook import TextbookChunk
        source=TextbookChunk(source="教材.txt",section="集合",text="集合的元素",terms=frozenset())
        with patch("orchestrator.retrieve_hybrid",return_value=[source]),patch("orchestrator.retrieve_figures",return_value=[]),\
             patch("orchestrator.expand_proof_sources",return_value=([source],None)),\
             patch("orchestrator.enrich_sources",return_value=([source],None)),\
             patch("orchestrator.complete_pdf_references",return_value=[]):
            return tutor.handle_turn("s","A包含元素1",learning_goal=self.point)

    def test_real_turn_question_never_projects_mastery_or_progress(self):
        tutor=self.make_tutor("question")
        result=self.turn(tutor)
        self.assertEqual(tutor.response_generator.generate.call_args.kwargs["memory_context"]["schema_version"],"memory-context-v1")
        self.assertEqual(result["memory_commit"]["status"],"committed")
        self.assertEqual(self.memory.get_state("s",self.point).mastery,.5)
        self.assertEqual(self.memory.get_state("s",self.point).steps_mastery,{"S1":.4})
        self.assertFalse(result["step_advanced"])
        self.assertEqual(self.memory.get_profile("s").teaching_effectiveness,{})

    def test_real_turn_independent_attempt_has_single_observation(self):
        result=self.turn(self.make_tutor("attempt"))
        self.assertAlmostEqual(result["student_state"]["mastery"],.58)
        self.assertEqual(self.count(EvidenceRow),1)
        self.assertFalse(result["step_advanced"])

    def test_real_turn_quality_rejection_leaves_no_diagnosis_or_revision(self):
        tutor=self.make_tutor("attempt",accepted=False)
        token=self.memory.repo.memory_token("s",self.point)
        result=self.turn(tutor)
        self.assertEqual(result["answer_status"],"quality_rejected")
        self.assertEqual(self.count(MemoryRevisionRow),0)
        self.assertEqual(self.count(EvidenceRow),0)
        self.assertEqual(self.memory.repo.memory_token("s",self.point),token)
        tutor.state_updater.update.assert_not_called()

    def test_real_turn_tutor_error_does_not_resave_rejected_state(self):
        token=self.memory.repo.memory_token("s",self.point)
        result=self.turn(self.make_tutor("attempt",rollback=True))
        self.assertEqual(result["memory_commit"]["status"],"rolled_back")
        self.assertEqual(self.memory.repo.memory_token("s",self.point),token)
        self.assertEqual(result["student_state"]["mastery"],.5)

    def test_behavior_after_chat_invalidates_old_independence_context(self):
        self.memory.commit_learning_turn(**self.args())
        self.assertIsNotNone(self.memory.repo.latest_learning_event("s",self.point))
        self.memory.append("s","user","请解释选区",selection_ref={"page":2})
        self.assertIsNone(self.memory.repo.latest_learning_event("s",self.point))

    def test_nested_submission_failure_does_not_leave_memory(self):
        with self.assertRaises(RuntimeError):
            with db.session_scope(immediate=True):
                self.memory.record_exercise_submission("s",self.point,"sub1","q1","v1",{}, {"parts":[]},False)
                raise RuntimeError("提交结果事务失败")
        self.assertEqual(self.count(LearningEventRow),0)

    def test_selection_exchange_is_atomic_and_uses_selected_section(self):
        reference={"document_id":"book","page":4,"section_title":"关系"}
        original=self.memory.repo.append_conversation
        def fail_assistant(student_id,role,*args,**kwargs):
            if role=="assistant":
                raise RuntimeError("对话写入失败")
            return original(student_id,role,*args,**kwargs)
        with patch.object(self.memory.repo,"append_conversation",side_effect=fail_assistant):
            with self.assertRaises(RuntimeError):
                self.memory.append_exchange("s","解释选区","解释",reference)
        self.assertEqual(self.count(ConversationRow),0)
        self.assertEqual(self.count(LearningEventRow),0)
        self.memory.append_exchange("s","解释选区","解释",reference)
        with self.factory() as session:
            row=session.scalar(select(LearningEventRow))
            self.assertEqual(row.knowledge_point,"关系")
        self.assertEqual(self.count(ConversationRow),2)


if __name__ == "__main__":
    unittest.main()
