"""规则题技能映射：临时数据库、真实规则批改及模拟教学输入。"""
import json
import unittest
from uuid import uuid4
from types import SimpleNamespace
from unittest.mock import patch
from sqlalchemy import select, func
from database.database import session_scope
from database.models import ExerciseSubmissionRow, ExerciseSkillObservationRow, LearningEventRow
from memory.memory_manager import MemoryManager
from models.student_state import StudentState
from knowledge.exercise_mapping import resolve_mapping, mapping_version
from knowledge.exercise_graders import evaluate_rule
from tests import test_memory_jobs as fixtures
from tests.test_memory_personalization import RecordingLLM
from agents.response_generator import ResponseGenerator
from agents.teaching_planner import TeachingPlanner
import practice_api as practice


class ExerciseSkillTests(unittest.TestCase):
    tearDown=fixtures.MemoryJobTests.tearDown
    make_tutor=fixtures.MemoryJobTests.make_tutor
    turn=fixtures.MemoryJobTests.turn

    def setUp(self):
        fixtures.MemoryJobTests.setUp(self)
        self.qid="ex-01-01-001"
        self.q=practice.question(self.qid)
        self.point=self.q["knowledge_point"]
        self.version=practice.catalog()["version"]
        self.before=StudentState(student_id="s",current_concept=self.point,mastery=.5)
        self.memory.save_state("s",self.point,self.before)
        self.plan=self.plan.model_copy(update={"goal":self.point})
        self.memory.save_lesson_plan("s",self.point,self.plan,{"S1":.4})
        self.memory.set_active_goal("s",self.point)

    def count(self, model):
        with session_scope() as session:return session.scalar(select(func.count()).select_from(model))

    def submit(self, answers, qid=None, sid="s", assisted=False, version=None, mutate=None):
        qid=qid or self.qid;q=practice.question(qid);version=version or self.version
        self.memory.ensure_student(sid)
        output={"parts":[]}
        for part in q["parts"]:
            if part["id"] not in answers:continue
            key=practice.keys().get(qid,{}).get(part["id"])
            result=evaluate_rule(part,answers[part["id"]],key) if key else {"part_id":part["id"],"method":"ai_assisted","confirmed":False,"score":100,"verdict":"correct"}
            if mutate:result=mutate(result)
            output["parts"].append(result)
        sub=uuid4().hex
        with session_scope(immediate=True) as session:
            session.add(ExerciseSubmissionRow(id=sub,student_id=sid,request_id=sub,question_id=qid,version=version,answers=answers,status="completed",result=output))
            self.memory.record_exercise_submission(sid,q["knowledge_point"],sub,qid,version,answers,output,assisted)
        return sub,output

    def test_all_rule_parts_have_fingerprint_bound_mapping(self):
        total=0;ids=set()
        for qid,parts in practice.keys().items():
            for pid in parts:
                mapping=resolve_mapping(qid,pid,self.version)
                self.assertIsNotNone(mapping,(qid,pid))
                self.assertEqual(mapping[0]["mapping_version"],mapping_version())
                ids.add(mapping[0]["skill_id"]);total+=1
        self.assertEqual(total,41);self.assertEqual(len(ids),15)
        self.assertIsNone(resolve_mapping(self.qid,"p6",self.version))

    def test_correct_independent_rule_item_changes_skill_not_whole_section(self):
        self.submit({"p1":["A"]})
        self.memory=MemoryManager()
        summary=self.memory.skill_summary("s",self.point)
        self.assertEqual(summary[0]["skill_id"],"set.determinacy")
        self.assertAlmostEqual(summary[0]["mastery_estimate"],.7)
        self.assertEqual(summary[0]["independent_items"],1)
        self.assertEqual(self.memory.get_state("s",self.point).mastery,.5)
        self.assertFalse(summary[0]["needs_review"])

    def test_wrong_item_yields_review_direction_not_confirmed_misconception(self):
        self.submit({"p4":["B"]})
        summary=self.memory.skill_summary("s",self.point)[0]
        self.assertAlmostEqual(summary["mastery_estimate"],.3)
        self.assertTrue(summary["needs_review"]);self.assertTrue(summary["diagnostic_targets"])
        self.assertEqual(self.memory.get_misconceptions("s",self.point),[])

    def test_assisted_and_unparseable_answers_do_not_measure_skill(self):
        self.submit({"p1":["A"]},assisted=True)
        self.submit({"p1":["不是集合","不是集合"]},qid="ex-01-01-002")
        self.assertEqual(self.memory.skill_summary("s",self.point),[])
        self.assertEqual(self.count(ExerciseSkillObservationRow),2)

    def test_stale_version_unknown_part_and_changed_content_are_blocked(self):
        self.submit({"p1":["A"]},version="0"*64)
        self.submit({"p6":["A"]})
        self.assertEqual(self.count(ExerciseSkillObservationRow),0)
        q=dict(self.q,text=self.q["text"]+"已修改")
        data=dict(practice.catalog(),by_id=dict(practice.catalog()["by_id"],**{self.qid:q}))
        with patch.object(practice,"catalog",return_value=data):
            self.assertIsNone(resolve_mapping(self.qid,"p1",self.version))

    def test_forged_rule_score_is_rechecked_against_server_answer_key(self):
        self.submit({"p1":["B"]},mutate=lambda r:dict(r,score=100,verdict="correct"))
        self.assertEqual(self.memory.skill_summary("s",self.point),[])
        with session_scope() as session:
            row=session.scalar(select(ExerciseSkillObservationRow))
            self.assertFalse(row.eligible);self.assertEqual(row.outcome,"unknown")

    def test_repeated_part_does_not_increase_independent_item_count(self):
        sub,out=self.submit({"p1":["A"]})
        self.memory.record_exercise_submission("s",self.point,sub,self.qid,self.version,{"p1":["A"]},out,False)
        self.submit({"p1":["A"]})
        self.assertEqual(self.count(ExerciseSkillObservationRow),2)
        summary=self.memory.skill_summary("s",self.point)[0]
        self.assertEqual(summary["independent_items"],1)
        self.assertAlmostEqual(summary["mastery_estimate"],.7)
        self.submit({"p2":["B"]})
        summary=self.memory.skill_summary("s",self.point)[0]
        self.assertEqual(summary["independent_items"],2)
        self.assertAlmostEqual(summary["mastery_estimate"],.82)

    def test_correct_retry_replaces_same_item_error_but_other_error_remains(self):
        self.submit({"p1":["B"],"p2":["A"]})
        self.submit({"p2":["B"]})
        summary=self.memory.skill_summary("s",self.point)[0]
        self.assertTrue(summary["needs_review"])
        self.submit({"p1":["A"]})
        self.assertFalse(self.memory.skill_summary("s",self.point)[0]["needs_review"])

    def test_truth_table_partial_result_has_limited_skill_scope(self):
        cells=[["1","1","1"],["0","1","1"],["1","0","1"],["0","0","1"]]
        self.submit({"p3":{"cells":cells,"note":""}},qid="ex-04-01-004")
        point=practice.question("ex-04-01-004")["knowledge_point"]
        item=self.memory.skill_summary("s",point)[0]
        self.assertEqual(item["skill_id"],"logic.compound_truth_table")
        self.assertAlmostEqual(item["mastery_estimate"],.6)
        self.assertTrue(item["needs_review"])
        self.assertEqual(self.memory.get_state("s",point).mastery,.5)

    def test_student_scope_delete_and_late_callback_do_not_resurrect(self):
        sub,out=self.submit({"p1":["A"]})
        self.submit({"p2":["B"]},sid="other")
        self.memory.forget_point("s",self.point)
        self.assertEqual(self.memory.skill_summary("s",self.point),[])
        self.assertTrue(self.memory.skill_summary("other",self.point))
        self.memory.record_exercise_submission("s",self.point,sub,self.qid,self.version,{"p1":["A"]},out,False)
        self.assertEqual(self.memory.skill_summary("s",self.point),[])
        self.assertEqual(self.count(ExerciseSubmissionRow),2)
        self.submit({"p1":["A"]})
        self.assertTrue(self.memory.skill_summary("s",self.point))

    def test_projection_failure_rolls_back_submission_event_and_evidence(self):
        before=self.count(ExerciseSubmissionRow)
        with patch.object(self.memory.repo,"record_exercise_skills",side_effect=RuntimeError("投影失败")):
            with self.assertRaises(RuntimeError):self.submit({"p1":["A"]})
        self.assertEqual(self.count(ExerciseSubmissionRow),before)
        self.assertEqual(self.count(LearningEventRow),0)
        self.assertEqual(self.count(ExerciseSkillObservationRow),0)

    def test_real_practice_worker_writes_skill_in_grading_transaction(self):
        sub=uuid4().hex
        with session_scope() as session:
            session.add(ExerciseSubmissionRow(id=sub,student_id="s",request_id=sub,question_id=self.qid,
                version=self.version,answers={"p1":["A"]},status="queued",result={}))
        main=SimpleNamespace(orchestrator=SimpleNamespace(memory=self.memory))
        with patch.dict("sys.modules",{"main":main}):practice.run_submission(sub)
        with session_scope() as session:
            self.assertEqual(session.get(ExerciseSubmissionRow,sub).status,"completed")
        self.assertEqual(self.memory.skill_summary("s",self.point)[0]["independent_items"],1)

    def queued_submission(self):
        main=SimpleNamespace(orchestrator=SimpleNamespace(memory=self.memory))
        tasks=practice.BackgroundTasks()
        body=practice.SubmitRequest(student_id="s",version=self.version,answers={"p1":["A"]},request_id=uuid4().hex)
        with patch.dict("sys.modules",{"main":main}), patch.object(practice,"student",return_value="s"):
            result=practice.submit(self.qid,body,tasks)
        self.assertEqual(result["result"],{})
        with session_scope() as session:
            self.assertEqual(session.get(ExerciseSubmissionRow,result["id"]).result["_memory_epoch"],
                self.memory.repo.memory_epoch("s",self.point))
        return result["id"],main

    def assert_late_grade_excluded(self, sub):
        with session_scope() as session:
            row=session.get(ExerciseSubmissionRow,sub)
            self.assertEqual(row.status,"completed")
            self.assertEqual(row.result["confirmed_score"],100)
        self.assertEqual(self.memory.skill_summary("s",self.point),[])
        self.assertTrue(self.memory.repo.memory_source_excluded("s","exercise",sub))
        self.memory.repo.sync_memory_index("s")
        self.assertEqual(self.memory.repo.get_event("s","submission:"+sub),None)
        self.assertNotIn(self.point,self.memory.memory_overview("s")["points"])

    def test_delete_while_submission_is_queued_preserves_score_without_memory(self):
        sub,main=self.queued_submission()
        self.memory.forget_point("s",self.point)
        with patch.dict("sys.modules",{"main":main}):practice.run_submission(sub)
        self.assert_late_grade_excluded(sub)
        new,main=self.queued_submission()
        with patch.dict("sys.modules",{"main":main}):practice.run_submission(new)
        self.assertTrue(self.memory.skill_summary("s",self.point))

    def test_delete_during_grading_preserves_score_without_memory(self):
        sub,main=self.queued_submission()
        original=practice.rule_grade
        def grade(*args):
            self.memory.forget_point("s",self.point)
            return original(*args)
        with patch.dict("sys.modules",{"main":main}),patch.object(practice,"rule_grade",side_effect=grade):
            practice.run_submission(sub)
        self.assert_late_grade_excluded(sub)

    def test_skill_gap_reaches_real_planner_generator_and_budgeted_context(self):
        self.submit({"p4":["B"]})
        self.memory=MemoryManager();tutor=self.make_tutor("question");llm=RecordingLLM()
        tutor.teaching_planner=TeachingPlanner(llm);tutor.response_generator=ResponseGenerator(llm)
        tutor.question_designer.design.return_value=None
        with patch("memory.retrieval._model",return_value=(None,None)):
            result=self.turn(tutor)
            context=self.memory.retrieve_context("s",title=self.point,question="集合元素",budget=1600)
        self.assertEqual(result["memory_commit"]["status"],"committed")
        self.assertIn("最近独立规则题提示待复习技能",llm.plans[-1][-1]["content"])
        self.assertIn("set.membership_subset",llm.messages[-1][-1]["content"])
        self.assertLessEqual(len(json.dumps(context,ensure_ascii=False)),1600)
        overview=self.memory.memory_overview("s",self.point)
        self.assertEqual(overview["detail"]["skills"][0]["skill_id"],"set.membership_subset")


if __name__=="__main__":unittest.main()
