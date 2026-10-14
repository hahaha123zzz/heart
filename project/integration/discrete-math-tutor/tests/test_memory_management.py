"""记忆管理：临时 SQLite 和本地 ASGI，禁止真实模型/生产 DB。"""
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from sqlalchemy import select
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests import test_memory_jobs as fixtures
from database.database import session_scope
from database.models import (Student,MemoryJobRow,MemoryArtifactRow,MemoryRevisionRow,LearningEventRow,ConversationRow,
    ExerciseSubmissionRow,MemoryChangeRow,MemoryExclusionRow,MemoryDocumentRow)
from memory.background_worker import MemoryWorker
from models.student_state import StudentState
from memory_api import router


class MemoryManagementTests(unittest.TestCase):
    setUp=fixtures.MemoryJobTests.setUp
    tearDown=fixtures.MemoryJobTests.tearDown
    args=fixtures.MemoryJobTests.args
    count=fixtures.MemoryJobTests.count
    enqueue=fixtures.MemoryJobTests.enqueue
    notes=fixtures.MemoryJobTests.notes
    make_tutor=fixtures.MemoryJobTests.make_tutor
    turn=fixtures.MemoryJobTests.turn

    def target(self,point=None,kind="set_element_confusion",student="s"):
        self.memory.ensure_student(student)
        return self.memory.add_hypothesis(student,point or self.point,kind,"混淆集合元素",.9)

    def test_view_includes_sources_and_only_requested_student(self):
        self.enqueue();a=self.target();self.target(student="other")
        overview=self.memory.memory_overview("s",self.point)
        self.assertEqual(len(overview["detail"]["misconceptions"]),1)
        self.assertEqual(overview["detail"]["misconceptions"][0]["id"],a.id)
        self.assertTrue(overview["detail"]["evidence"][0]["event_id"])

    def test_user_dispute_is_statement_not_mastery_and_affects_one_target(self):
        a=self.target();b=self.target(kind="relation_function_confusion")
        before=self.memory.get_state("s",self.point).mastery
        correction=self.memory.dispute_misconception("s",a.id,"我能区分元素和集合，这个判断不符合我的情况")
        items={m.id:m for m in self.memory.get_misconceptions("s",self.point)}
        self.assertEqual(items[a.id].status,"dismissed");self.assertEqual(items[b.id].status,"supported")
        self.assertEqual(self.memory.get_state("s",self.point).mastery,before)
        self.assertEqual(correction["verification"],"student_statement")
        with patch("memory.retrieval._model",return_value=(None,None)):
            context=self.memory.retrieve_context("s",title=self.point,question="集合元素")
        self.assertTrue(any(item.get("evidence_type")=="user_correction" for item in context["items"]))

    def test_foreign_dispute_and_blank_note_are_rejected(self):
        a=self.target(student="other")
        with self.assertRaises(LookupError):self.memory.dispute_misconception("s",a.id,"否认")
        b=self.target()
        with self.assertRaises(ValueError):self.memory.dispute_misconception("s",b.id," ")
        self.assertEqual(self.memory.get_misconceptions("s",self.point)[0].status,"supported")

    def test_preferences_have_explicit_source_and_clear_old_snapshots(self):
        self.memory.set_preferences("s",{"answer_length":1})
        self.enqueue()
        self.assertEqual(self.memory.memory_overview("s")["preferences"][0]["source"],"explicit_user")
        self.memory.forget_preference("s","answer_length")
        self.assertNotIn("answer_length",self.memory.get_profile("s").preferences)
        with self.factory() as session:
            rows=session.scalars(select(MemoryRevisionRow)).all()
            for row in rows:
                for snapshot in (row.before,row.after):
                    self.assertTrue(all("answer_length" not in value["preferences"] for value in snapshot["learner_profiles"]))
            self.assertFalse(any(r.action=="set_preference" for r in session.scalars(select(MemoryChangeRow))))

    def test_invalid_preference_cannot_overwrite_profile(self):
        for values in ({"unknown":.5},{"answer_length":True},{"answer_length":2},{"answer_length":float("nan")}):
            with self.assertRaises(ValueError):self.memory.set_preferences("s",values)
        self.assertEqual(self.memory.get_profile("s").preferences,{})

    def test_forget_point_removes_sources_jobs_and_index(self):
        self.enqueue();self.target();MemoryWorker(self.memory.repo).run_once()
        self.memory.repo.sync_memory_index("s")
        self.assertTrue(self.memory.repo.memory_documents("s"))
        self.memory.forget_point("s",self.point)
        self.assertEqual(self.memory.memory_overview("s")["points"],[])
        for model in (LearningEventRow,ConversationRow,MemoryJobRow,MemoryArtifactRow,MemoryDocumentRow):
            self.assertEqual(self.count(model),0)
        with patch("memory.retrieval._model",return_value=(None,None)):
            context=self.memory.retrieve_context("s",title=self.point,question="集合元素")
        self.assertEqual(context["items"],[]);self.assertEqual(context["learning_states"],[])

    def test_other_point_and_other_student_survive_and_snapshots_scrubbed(self):
        a=self.target();self.enqueue()
        self.memory.ensure_student("other");self.memory.append("other","user","集合私密记录")
        self.point="关系";self.memory.save_state("s",self.point,StudentState(student_id="s",current_concept=self.point))
        self.enqueue()
        self.memory.forget_point("s","集合")
        self.assertEqual(self.memory.memory_overview("s")["points"],["关系"])
        self.assertTrue(self.memory.get_history("other"))
        with self.factory() as session:
            for row in session.scalars(select(MemoryRevisionRow)):
                for snap in (row.before,row.after):
                    self.assertFalse(any(v.get("knowledge_point")=="集合" or v.get("misconception_id")==a.id for vs in snap.values() for v in vs))

    def test_delete_prevents_old_turn_and_allows_new_epoch(self):
        self.enqueue();old=self.args()
        self.memory.forget_point("s",self.point)
        self.assertEqual(self.memory.commit_learning_turn(**old)["status"],"forgotten")
        self.assertEqual(self.count(ConversationRow),0)
        fresh=self.args();fresh["expected_epoch"]=self.memory.repo.memory_epoch("s",self.point)
        self.assertEqual(self.memory.commit_learning_turn(**fresh)["status"],"committed")

    def test_background_and_vector_late_results_do_not_resurrect(self):
        self.enqueue();claim=self.memory.repo.claim_memory_job()
        self.memory.repo.sync_memory_index("s");doc=self.memory.repo.memory_documents("s")[0]
        self.memory.forget_point("s",self.point)
        self.assertFalse(self.memory.repo.finish_memory_job(claim,self.notes(claim)))
        self.memory.repo.save_memory_vectors("s",[(doc["id"],doc["content_hash"],[1.,0.])],"fake")
        self.assertEqual(self.memory.repo.memory_documents("s"),[])

    def test_old_exercise_preserved_but_cannot_reenter_memory(self):
        def submission(sid):
            with session_scope() as session:
                session.add(ExerciseSubmissionRow(id=sid,student_id="s",request_id=sid,question_id="q1",version="v1",answers={"a":"集合元素"},status="completed",result={"parts":[]}))
            self.memory.record_exercise_submission("s",self.point,sid,"q1","v1",{"a":"集合元素"},{"parts":[]},False)
        submission("old")
        self.memory.forget_point("s",self.point)
        self.memory.repo.sync_memory_index("s")
        self.assertEqual(self.memory.repo.memory_documents("s"),[])
        self.assertEqual(self.count(ExerciseSubmissionRow),1)
        self.assertEqual(self.count(MemoryExclusionRow),1)
        self.memory.record_exercise_submission("s",self.point,"old","q1","v1",{"a":"集合元素"},{"parts":[{"part_id":"a","confirmed":True,"method":"rule"}]},False)
        self.assertEqual(self.count(LearningEventRow),0)
        submission("new");self.memory.repo.sync_memory_index("s")
        self.assertTrue(any(d["source_id"]=="new" for d in self.memory.repo.memory_documents("s")))
        self.assertFalse(any(d["source_id"]=="old" for d in self.memory.repo.memory_documents("s")))

    def test_delete_transaction_failure_restores_all_records(self):
        self.enqueue();token=self.memory.get_version("s",self.point)
        original=self.memory.repo.sync_memory_index;calls=0
        def fail_on_publish(student):
            nonlocal calls
            calls+=1
            if calls>=2:raise RuntimeError("索引提交失败")
            return original(student)
        with patch.object(self.memory.repo,"sync_memory_index",side_effect=fail_on_publish):
            with self.assertRaises(RuntimeError):self.memory.forget_point("s",self.point)
        self.assertEqual(self.count(MemoryJobRow),1);self.assertEqual(self.count(ConversationRow),2)
        self.assertEqual(self.memory.get_version("s",self.point),token)

    def test_legacy_selection_with_known_section_is_deletable(self):
        self.memory.repo.append_conversation("s","user","集合选区",selection_ref={"section_title":"集合","page":4})
        self.assertIn("集合",self.memory.memory_overview("s")["points"])
        self.memory.forget_point("s","集合")
        self.assertEqual(self.count(ConversationRow),0)

    def test_api_scope_validation_and_actual_mutations(self):
        with session_scope() as session:session.get(Student,"s").account_type="test"
        a=self.target();self.enqueue()
        app=FastAPI();app.include_router(router)
        fake=SimpleNamespace(orchestrator=SimpleNamespace(memory=self.memory))
        with patch.dict("sys.modules",{"main":fake}),TestClient(app) as client:
            self.assertEqual(client.get("/api/students/s/memory").status_code,200)
            self.assertEqual(client.get("/api/students/missing/memory").status_code,404)
            self.memory.ensure_student("prod")
            self.assertEqual(client.get("/api/students/prod/memory").status_code,403)
            base="/api/students/s/memory"
            self.assertEqual(client.post(base+f"/misconceptions/{a.id}/correction",json={"note":" ","verification":"rule_verified"}).status_code,422)
            self.assertEqual(client.post(base+f"/misconceptions/{a.id}/correction",json={"note":"这个判断不符合我的情况"}).status_code,200)
            self.assertEqual(client.delete(base+"/points",params={"point":"未知"}).status_code,404)
            self.assertEqual(client.delete(base+"/points",params={"point":"集合"}).status_code,200)

    def test_pdf_selection_deleted_mid_generation_is_not_saved(self):
        from unittest.mock import Mock
        from agents.pdf_selection_tutor import explain_selection
        self.enqueue()
        tutor=SimpleNamespace(memory=self.memory,llm=Mock(),context_sufficiency=Mock(),quality_checker=Mock())
        from models.task_understanding import TaskUnderstanding
        tutor.conversation_router=Mock()
        tutor.conversation_router.route.return_value=TaskUnderstanding(student_move="question")
        tutor.context_sufficiency.check.return_value=SimpleNamespace(allowed=True,model_dump=lambda:{})
        tutor.quality_checker.check.return_value=SimpleNamespace(passed=True,model_dump=lambda:{})
        def generating(*args,**kwargs):
            self.memory.forget_point("s",self.point)
            return "基于旧学习记忆的解释"
        tutor.llm.chat.side_effect=generating
        reference={"document_id":"book","version":"v1","chapter_id":1,"section_id":1,"section_title":self.point,"source":"教材PDF","image_refs":[],"rects":[{"page":4}]}
        selection=SimpleNamespace(document_id="book",rects=[SimpleNamespace(page=4)])
        resolved={"section":{"title":self.point},"text":"集合定义","context":"教材上下文","images":[],"reference":reference}
        with patch("agents.pdf_selection_tutor.resolve_selection",return_value=resolved),patch("memory.retrieval._model",return_value=(None,None)):
            result=explain_selection(tutor,"s","解释选区",selection,"production")
        self.assertEqual(result["answer_status"],"memory_deleted")
        self.assertEqual(self.count(ConversationRow),0)

    def test_real_turn_deleted_mid_generation_is_not_published(self):
        self.enqueue();tutor=self.make_tutor("attempt")
        def generating(*args,**kwargs):
            self.memory.forget_point("s",self.point)
            return "基于已删除记忆的旧回答"
        tutor.response_generator.generate.side_effect=generating
        result=self.turn(tutor)
        self.assertEqual(result["answer_status"],"memory_deleted")
        self.assertNotIn("旧回答",result["reply"])
        self.assertEqual(self.count(ConversationRow),0)
        self.assertEqual(self.count(MemoryJobRow),0)


if __name__=="__main__":unittest.main()
