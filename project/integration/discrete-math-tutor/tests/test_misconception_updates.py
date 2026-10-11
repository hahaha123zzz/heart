"""逐项误区反证检查；内存数据库与模拟代理，不调用真实模型。"""
import unittest
from unittest.mock import patch
from sqlalchemy import select
from tests import test_memory_events as event_fixtures
from database.models import MisconceptionObservationRow, LearningEventRow
from models.misconception_update import MisconceptionUpdate
from agents.evidence_extractor import MisconceptionHypothesis
from agents.state_updater import _parse_misconception_updates
from memory.evidence_policy import EvidenceDecision


class MisconceptionUpdateTests(unittest.TestCase):
    setUp = event_fixtures.MemoryEventTests.setUp
    tearDown = event_fixtures.MemoryEventTests.tearDown
    args = event_fixtures.MemoryEventTests.args
    count = event_fixtures.MemoryEventTests.count
    make_tutor = event_fixtures.MemoryEventTests.make_tutor
    turn = event_fixtures.MemoryEventTests.turn

    def target(self, kind="set_element_confusion", point=None, student="s", confirmed=False):
        self.memory.ensure_student(student)
        item = self.memory.add_hypothesis(student, point or self.point, kind, "误区：" + kind, .9)
        if confirmed:
            for _ in range(2):
                item = self.memory.add_hypothesis(student, point or self.point, kind, "误区", .9)
        return item

    def correction(self, item, quote="1是A的元素而不是子集", action="resolve"):
        return MisconceptionUpdate(misconception_id=item.id, action=action, source_quote=quote, reason="区分了元素与集合")

    def commit(self, item, quote="1是A的元素而不是子集", action="resolve", **changes):
        args = self.args()
        args.update(message=quote, evidence=[], misconception_updates=[self.correction(item, quote, action)])
        args.update(changes)
        return self.memory.commit_learning_turn(**args)

    def status(self, item, student="s", point=None):
        return next(m for m in self.memory.get_misconceptions(student, point or self.point) if m.id == item.id).status

    def test_two_distinct_counter_events_only_resolve_target(self):
        a=self.target(); b=self.target("relation_function_confusion")
        first=self.commit(a)
        self.assertEqual(first["misconception_updates"][0]["outcome"], "pending")
        self.commit(a, "2属于集合B，单元素集合才是子集")
        self.assertEqual(self.status(a), "resolved")
        self.assertEqual(self.status(b), "supported")
        self.assertEqual(self.memory.get_state("s", self.point).mastery, .6)
        self.assertEqual(self.count(MisconceptionObservationRow), 2)

    def test_duplicate_event_and_copied_quote_do_not_add_votes(self):
        a=self.target(); args=self.args(); args.update(evidence=[], misconception_updates=[self.correction(a)], message="1是A的元素而不是子集")
        self.memory.commit_learning_turn(**args)
        self.assertEqual(self.memory.commit_learning_turn(**args)["status"], "duplicate")
        result=self.commit(a)
        self.assertEqual(result["misconception_updates"][0]["distinct_counter_evidence"], 1)
        self.assertEqual(self.status(a), "supported")

    def test_new_support_interrupts_counter_streak_and_reopens(self):
        a=self.target(); self.commit(a)
        quote="集合A是元素1"
        hypo=MisconceptionHypothesis(type=a.type,description=a.description,source_quote=quote,confidence=.9)
        args=self.args(); args.update(message=quote,evidence=[],hypotheses=[(hypo,a.id)])
        self.memory.commit_learning_turn(**args)
        self.assertEqual(self.commit(a,"元素3和集合不同")["misconception_updates"][0]["outcome"],"pending")
        self.commit(a,"元素4是集合成员")
        self.assertEqual(self.status(a),"resolved")
        args=self.args();args.update(message=quote,evidence=[],hypotheses=[(hypo,a.id)])
        result=self.memory.commit_learning_turn(**args)
        self.assertEqual(result["misconception_updates"][0]["outcome"],"reopened")
        self.assertEqual(self.commit(a)["misconception_updates"][0]["distinct_counter_evidence"],1)

    def test_support_and_counter_same_event_is_conflict(self):
        a=self.target(); quote="1是A的元素而不是子集"
        hypo=MisconceptionHypothesis(type=a.type,description=a.description,source_quote=quote,confidence=.9)
        result=self.commit(a,hypotheses=[(hypo,a.id)])
        self.assertEqual(result["misconception_updates"][0]["outcome"],"conflict")
        self.assertEqual(self.memory.get_misconceptions("s",self.point)[0].evidence_count,1)
        self.assertEqual(self.status(a),"supported")

    def test_opposite_corrections_are_conflict(self):
        a=self.target(); quote="1是A的元素而不是子集"
        result=self.commit(a,misconception_updates=[self.correction(a),self.correction(a,action="dismiss")])
        self.assertEqual(result["misconception_updates"][0]["outcome"],"conflict")
        self.assertEqual(self.status(a),"supported")

    def test_foreign_student_and_point_are_rejected(self):
        a=self.target(student="other"); b=self.target(point="关系")
        for item in (a,b):
            result=self.commit(item)
            self.assertEqual(result["misconception_updates"][0]["outcome"],"rejected")
        self.assertEqual(self.count(MisconceptionObservationRow),0)
        self.assertEqual(self.status(a,student="other"),"supported")
        self.assertEqual(self.status(b,point="关系"),"supported")

    def test_ungrounded_acknowledgment_and_assistance_rejected(self):
        a=self.target()
        cases=[dict(message="教材里说了"),dict(message="我懂了",misconception_updates=[self.correction(a,"我懂了")]),
               dict(decision=EvidenceDecision(False,False,"提示后作答"))]
        for change in cases:
            self.assertEqual(self.commit(a,**change)["misconception_updates"][0]["outcome"],"rejected")
        self.assertEqual(self.count(MisconceptionObservationRow),0)

    def test_dismiss_candidate_but_confirmed_requires_review(self):
        a=self.target(); self.commit(a,action="dismiss");self.commit(a,"1是元素，集合才可能是子集",action="dismiss")
        self.assertEqual(self.status(a),"dismissed")
        b=self.target("relation_function_confusion",confirmed=True)
        result=self.commit(b,action="dismiss")
        self.assertEqual(result["misconception_updates"][0]["outcome"],"review_required")
        self.assertEqual(self.status(b),"confirmed")

    def test_trusted_rule_decision_can_resolve_once(self):
        a=self.target();self.commit(a,decision=EvidenceDecision(True,True,"服务端规则核验",verification="rule_verified"))
        self.assertEqual(self.status(a),"resolved")

    def test_parser_rejects_invalid_ids_and_ignores_claimed_verification(self):
        valid={"misconception_id":1,"action":"resolve","source_quote":"学生原文","reason":"反证","verification":"rule_verified"}
        for bad_id in (0,True,"1"):
            self.assertEqual(_parse_misconception_updates([valid|{"misconception_id":bad_id}]),[])
        self.assertEqual(_parse_misconception_updates({}),[])
        self.assertEqual(_parse_misconception_updates([valid|{"action":"delete"}]),[])
        self.assertFalse(hasattr(_parse_misconception_updates([valid])[0],"verification"))

    def test_atomic_failure_rolls_back_counter_and_status(self):
        a=self.target(); self.commit(a)
        token=self.memory.get_version("s",self.point)
        with patch.object(self.memory.repo,"add_revision",side_effect=RuntimeError("注入事务失败")):
            with self.assertRaises(RuntimeError):
                self.commit(a,"2是元素而不是子集")
        self.assertEqual(self.status(a),"supported")
        self.assertEqual(self.count(MisconceptionObservationRow),1)
        self.assertEqual(self.memory.get_version("s",self.point),token)

    def test_version_conflict_and_tutor_error_skip_counter(self):
        a=self.target();args=self.args();args.update(misconception_updates=[self.correction(a)],message="1是A的元素而不是子集")
        self.memory.save_state("s",self.point,self.before.model_copy(update={"mastery":.8}))
        self.assertEqual(self.memory.commit_learning_turn(**args)["status"],"conflict")
        self.assertEqual(self.commit(a,tutor_error="讲解有误")["status"],"rolled_back")
        self.assertEqual(self.count(MisconceptionObservationRow),0)

    def test_real_turn_wires_updates_and_legacy_boolean_does_not_clear(self):
        a=self.target();b=self.target("relation_function_confusion")
        tutor=self.make_tutor("attempt")
        tutor.state_updater.update.return_value.misconception_updates=[self.correction(a,"A包含元素1")]
        tutor.state_updater.update.return_value.resolve_misconceptions=True
        result=self.turn(tutor)
        self.assertEqual(result["memory_commit"]["misconception_updates"][0]["outcome"],"pending")
        self.assertEqual(self.status(a),"supported");self.assertEqual(self.status(b),"supported")
        tutor=self.make_tutor("question")
        tutor.state_updater.update.return_value.misconception_updates=[self.correction(a,"A包含元素1")]
        self.assertEqual(self.turn(tutor)["memory_commit"]["misconception_updates"][0]["outcome"],"rejected")

    def test_resolved_support_is_hidden_but_correction_history_retained(self):
        a=self.target();self.commit(a);self.commit(a,"2是元素而非子集")
        with patch("memory.retrieval._model",return_value=(None,None)):
            context=self.memory.retrieve_context("s",title=self.point,question="元素和集合")
        evidence=[item for item in context["items"] if item["source"]["kind"]=="evidence"]
        self.assertFalse(any(item.get("evidence_type")=="misconception" for item in evidence))
        self.assertTrue(any(item.get("evidence_type")=="misconception_counter" for item in evidence))

    def test_quality_rejection_and_student_deletion(self):
        a=self.target();tutor=self.make_tutor("attempt",accepted=False)
        tutor.state_updater.update.return_value.misconception_updates=[self.correction(a,"A包含元素1")]
        self.assertEqual(self.turn(tutor)["answer_status"],"quality_rejected")
        self.assertEqual(self.count(MisconceptionObservationRow),0)
        self.commit(a);self.memory.reset("s")
        self.assertEqual(self.count(MisconceptionObservationRow),0)


if __name__ == "__main__":
    unittest.main()
