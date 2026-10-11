"""持久记忆任务：临时文件 SQLite、模拟模型，包含真实线程领取竞争。"""
import asyncio
import datetime as dt
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from database import database as db
from database.models import Base, MemoryJobRow, MemoryArtifactRow, LearningEventRow, EvidenceRow, ConversationRow
from database.memory_jobs import utcnow, LEASE_SECONDS
from memory.memory_manager import MemoryManager
from memory.background_worker import MemoryWorker, memory_lifespan
from models.student_state import StudentState
from models.lesson_plan import LessonPlan, LessonStep
from tests import test_memory_events as fixtures


class MemoryJobTests(unittest.TestCase):
    args=fixtures.MemoryEventTests.args
    count=fixtures.MemoryEventTests.count
    make_tutor=fixtures.MemoryEventTests.make_tutor
    turn=fixtures.MemoryEventTests.turn

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.engine=create_engine("sqlite:///"+str(Path(self.temp.name)/"memory.db"),connect_args={"check_same_thread":False})
        @event.listens_for(self.engine,"connect")
        def fk(connection,_):
            connection.execute("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(self.engine)
        self.factory=sessionmaker(bind=self.engine,autoflush=False,expire_on_commit=False)
        self.patch=patch.object(db,"SessionLocal",self.factory);self.patch.start()
        self.memory=MemoryManager();self.memory.ensure_student("s")
        self.point="集合"
        self.before=StudentState(student_id="s",current_concept=self.point,mastery=.5,steps_mastery={"S1":.4})
        self.plan=LessonPlan(goal=self.point,steps=[LessonStep(step_id="S1",objective="辨认集合")],current_step="S1")
        self.memory.save_state("s",self.point,self.before)
        self.memory.save_lesson_plan("s",self.point,self.plan,self.before.steps_mastery)

    def tearDown(self):
        self.patch.stop();self.engine.dispose();self.temp.cleanup()

    def enqueue(self):
        args=self.args();result=self.memory.commit_learning_turn(**args)
        return args,result["memory_job_id"]

    def notes(self, claim):
        event=claim["source"]["event"]
        return [{"event_id":event["id"],"quote":event["payload"]["content"]}]

    def test_atomic_enqueue_and_duplicate_event(self):
        args,jid=self.enqueue()
        self.assertEqual(self.memory.commit_learning_turn(**args)["status"],"duplicate")
        self.assertEqual(self.memory.repo.enqueue_memory_job("s",args["event_id"]),jid)
        self.assertEqual(self.count(MemoryJobRow),1)
        token=self.memory.get_version("s",self.point)
        with patch.object(self.memory.repo,"enqueue_memory_job",side_effect=RuntimeError("入队失败")):
            with self.assertRaises(RuntimeError):
                self.memory.commit_learning_turn(**self.args())
        self.assertEqual(self.count(MemoryJobRow),1)
        self.assertEqual(self.memory.get_version("s",self.point),token)

    def test_two_threads_only_one_can_claim(self):
        self.enqueue();barrier=threading.Barrier(2)
        def claim():
            barrier.wait()
            return self.memory.repo.claim_memory_job()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(claim) for _ in range(2)]
            results=[future.result() for future in futures]
        self.assertEqual(sum(value is not None for value in results),1)

    def test_expired_lease_reclaimed_and_late_worker_rejected(self):
        _,jid=self.enqueue();now=utcnow()
        old=self.memory.repo.claim_memory_job(now)
        self.assertIsNone(self.memory.repo.claim_memory_job(now+dt.timedelta(seconds=10)))
        later=now+dt.timedelta(seconds=LEASE_SECONDS+1)
        new=self.memory.repo.claim_memory_job(later)
        self.assertNotEqual(old["token"],new["token"])
        self.assertFalse(self.memory.repo.finish_memory_job(old,self.notes(old),now=later))
        self.assertFalse(self.memory.repo.fail_memory_job(old,now=later))
        self.assertTrue(self.memory.repo.finish_memory_job(new,self.notes(new),now=later))
        self.assertEqual(self.count(MemoryArtifactRow),1)
        self.assertEqual(self.memory.repo.memory_job_status("s",jid)["attempts"],2)

    def test_expired_lease_cannot_publish_without_new_claim(self):
        self.enqueue();now=utcnow();claim=self.memory.repo.claim_memory_job(now)
        self.assertFalse(self.memory.repo.finish_memory_job(claim,self.notes(claim),now=now+dt.timedelta(seconds=91)))
        self.assertEqual(self.count(MemoryArtifactRow),0)

    def test_backoff_three_attempts_then_explicit_replay(self):
        _,jid=self.enqueue();now=utcnow()
        for attempt in range(1,4):
            claim=self.memory.repo.claim_memory_job(now)
            self.assertIsNotNone(claim)
            self.memory.repo.fail_memory_job(claim,now)
            self.assertIsNone(self.memory.repo.claim_memory_job(now+dt.timedelta(seconds=1)))
            now+=dt.timedelta(seconds=5*2**attempt)
        status=self.memory.repo.memory_job_status("s",jid)
        self.assertEqual(status["status"],"failed")
        self.assertEqual(status["last_error"],"generation_failed")
        self.assertFalse(self.memory.repo.replay_memory_job("other",jid))
        self.assertTrue(self.memory.repo.replay_memory_job("s",jid))
        self.assertEqual(self.memory.repo.memory_job_status("s",jid)["attempts"],0)
        self.assertIsNotNone(self.memory.repo.claim_memory_job(now))

    def test_three_crashed_leases_eventually_fail(self):
        _,jid=self.enqueue();now=utcnow()
        for _ in range(3):
            self.assertIsNotNone(self.memory.repo.claim_memory_job(now))
            now+=dt.timedelta(seconds=91)
        self.assertIsNone(self.memory.repo.claim_memory_job(now))
        self.assertEqual(self.memory.repo.memory_job_status("s",jid)["status"],"failed")

    def test_invalid_source_canceled_before_model(self):
        args,jid=self.enqueue()
        with db.session_scope() as session:
            session.get(LearningEventRow,args["event_id"]).status="rolled_back"
        self.assertIsNone(self.memory.repo.claim_memory_job())
        self.assertEqual(self.memory.repo.memory_job_status("s",jid)["status"],"canceled")

    def test_source_changes_while_generating_do_not_publish_old_content(self):
        args,jid=self.enqueue();claim=self.memory.repo.claim_memory_job()
        with db.session_scope() as session:
            row=session.get(LearningEventRow,args["event_id"])
            row.payload=dict(row.payload,content="更正后的学生原文")
            session.get(ConversationRow,row.payload["conversation_ids"][0]).content="更正后的学生原文"
        self.assertFalse(self.memory.repo.finish_memory_job(claim,self.notes(claim)))
        self.assertEqual(self.count(MemoryArtifactRow),0)
        self.assertEqual(self.memory.repo.memory_job_status("s",jid)["last_error"],"source_changed")
        new=self.memory.repo.claim_memory_job(utcnow()+dt.timedelta(seconds=6))
        self.assertTrue(self.memory.repo.finish_memory_job(new,self.notes(new)))
        self.assertEqual(self.memory.repo.background_memories("s",self.point)[0]["content"]["notes"][0]["quote"],"更正后的学生原文")

    def test_evidence_change_invalidates_completed_artifact(self):
        self.enqueue();claim=self.memory.repo.claim_memory_job()
        self.memory.repo.finish_memory_job(claim,self.notes(claim))
        self.assertTrue(self.memory.repo.background_memories("s",self.point))
        with db.session_scope() as session:
            row=session.scalar(select(EvidenceRow));row.content="推断已更正"
        self.assertEqual(self.memory.repo.background_memories("s",self.point),[])

    def test_teacher_invalidated_blocks_published_reflection(self):
        teacher,_=self.enqueue();self.enqueue()
        while MemoryWorker(self.memory.repo).run_once():
            pass
        with db.session_scope() as session:
            session.get(LearningEventRow,teacher["event_id"]).status="rolled_back"
        self.assertEqual(self.memory.repo.background_memories("s",self.point),[])

    def test_deleted_original_conversation_invalidates_summary(self):
        args,_=self.enqueue();MemoryWorker(self.memory.repo).run_once()
        with db.session_scope() as session:
            event=session.get(LearningEventRow,args["event_id"])
            session.delete(session.get(ConversationRow,event.payload["conversation_ids"][0]))
        self.assertEqual(self.memory.repo.background_memories("s",self.point),[])

    def test_delete_student_during_generation_does_not_resurrect_memory(self):
        self.enqueue();claim=self.memory.repo.claim_memory_job()
        self.memory.reset("s")
        self.assertFalse(self.memory.repo.finish_memory_job(claim,self.notes(claim)))
        self.assertEqual(self.count(MemoryJobRow),0)
        self.assertEqual(self.count(MemoryArtifactRow),0)
        self.assertEqual(self.memory.repo.background_memories("s",self.point),[])

    def test_artifact_reading_scope_and_replay_upsert(self):
        _,jid=self.enqueue();worker=MemoryWorker(self.memory.repo);worker.run_once()
        self.assertEqual(self.memory.repo.background_memories("other",self.point),[])
        self.assertEqual(self.memory.repo.background_memories("s","关系"),[])
        self.assertTrue(self.memory.repo.replay_memory_job("s",jid))
        self.assertEqual(self.memory.repo.background_memories("s",self.point),[])
        worker.run_once();self.assertEqual(self.count(MemoryArtifactRow),1)

    def test_model_call_outside_transaction_and_validated_original_quotes(self):
        self.enqueue();model=Mock()
        def generate(messages,**kwargs):
            self.assertIsNone(db._current_session.get())
            self.assertEqual(kwargs["timeout"],20);self.assertEqual(kwargs["retries"],0)
            event=json.loads(messages[1]["content"])[0]
            return {"notes":[{"event_id":event["event_id"],"quote":event["student_text"]}]}
        model.chat_json.side_effect=generate
        token=self.memory.get_version("s",self.point)
        self.assertTrue(MemoryWorker(self.memory.repo,model).run_once())
        self.assertEqual(self.memory.get_version("s",self.point),token)
        self.assertEqual(self.memory.repo.background_memories("s",self.point)[0]["content"]["generation_mode"],"llm")

    def test_hallucinated_quote_foreign_event_and_extra_fields_are_rejected(self):
        for notes in ([{"event_id":"foreign","quote":"A包含元素1"}],
                      [{"event_id":"will_replace","quote":"模型编造的学生能力"}],
                      [{"event_id":"will_replace","quote":"A包含元素1","verification":"rule_verified"}]):
            args,jid=self.enqueue()
            notes=[dict(note,event_id=args["event_id"]) if note["event_id"]=="will_replace" else note for note in notes]
            model=Mock();model.chat_json.return_value={"notes":notes}
            MemoryWorker(self.memory.repo,model).run_once()
            self.assertEqual(self.memory.repo.memory_job_status("s",jid)["status"],"queued")
        self.assertEqual(self.count(MemoryArtifactRow),0)

    def test_failure_records_only_safe_error_code(self):
        _,jid=self.enqueue();model=Mock();model.chat_json.side_effect=RuntimeError("敏感配置文本")
        MemoryWorker(self.memory.repo,model).run_once()
        self.assertEqual(self.memory.repo.memory_job_status("s",jid)["last_error"],"generation_failed")

    def test_publish_transaction_failure_leaves_no_artifact(self):
        self.enqueue();claim=self.memory.repo.claim_memory_job()
        with self.assertRaises(RuntimeError):
            with db.session_scope(immediate=True):
                self.memory.repo.finish_memory_job(claim,self.notes(claim))
                raise RuntimeError("发布失败")
        self.assertEqual(self.count(MemoryArtifactRow),0)

    def test_context_budget_and_quality_rejection(self):
        self.enqueue();MemoryWorker(self.memory.repo).run_once()
        with patch("memory.retrieval._model",return_value=(None,None)):
            context=self.memory.retrieve_context("s",title=self.point,question="集合",budget=6000)
            compact=self.memory.retrieve_context("s",title=self.point,question="集合",budget=1500)
        self.assertTrue(context["background_memory"])
        self.assertLessEqual(len(json.dumps(compact,ensure_ascii=False)),1500)
        tutor=self.make_tutor("attempt",accepted=False);self.turn(tutor)
        self.assertEqual(self.count(MemoryJobRow),1)

    def test_worker_can_stop_without_waiting_for_poll_interval(self):
        ready=threading.Event();repo=Mock()
        def empty():
            ready.set();return None
        repo.claim_memory_job.side_effect=empty
        worker=MemoryWorker(repo,interval=100)
        worker.start();self.assertTrue(ready.wait(2));self.assertTrue(worker.stop(timeout=2))
        self.assertFalse(worker.status()["running"])

    def test_service_lifespan_starts_and_stops_worker_and_can_disable(self):
        app=SimpleNamespace(state=SimpleNamespace(memory=self.memory,memory_llm=Mock()))
        async def exercise():
            with patch.dict("os.environ",{"MEMORY_WORKER_ENABLED":"1","MEMORY_REFLECTION_LLM":"0"}),patch("memory.background_worker.MemoryWorker") as factory:
                async with memory_lifespan(app):
                    factory.return_value.start.assert_called_once()
                    self.assertIsNone(factory.call_args.args[1])
                factory.return_value.stop.assert_called_once()
            with patch.dict("os.environ",{"MEMORY_WORKER_ENABLED":"0"}),patch("memory.background_worker.MemoryWorker") as factory:
                async with memory_lifespan(app):
                    self.assertIsNone(app.state.memory_worker)
                factory.assert_not_called()
        asyncio.run(exercise())


if __name__=="__main__":
    unittest.main()
