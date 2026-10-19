"""澄清状态、幂等和删除边界：临时 SQLite，不调用外部模型。"""
import datetime as dt
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from sqlalchemy import create_engine, event, select, func
from sqlalchemy.orm import sessionmaker
from database import database as db
from database.models import Base, LearningTaskRow, TaskRequestRow, ConversationRow
from database.learning_tasks import LearningTaskRepository, TaskConflict, now
from agents.task_service import TaskService
from memory.memory_manager import MemoryManager
from models.chat_request import ChatRequest
from models.task_understanding import TaskUnderstanding


class ClarificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine("sqlite:///" + self.temp.name.replace("\\", "/") + "/test.db", connect_args={"check_same_thread": False})
        @event.listens_for(self.engine, "connect")
        def fk(connection, _): connection.execute("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        self.patch = patch.object(db, "SessionLocal", self.factory); self.patch.start()
        self.memory = MemoryManager(); self.memory.ensure_student("s", account_type="production")
        self.repo = LearningTaskRepository()
        self.service = TaskService(SimpleNamespace(memory=self.memory), self.repo)
        self.calls = []

    def tearDown(self):
        self.patch.stop(); self.engine.dispose(); self.temp.cleanup()

    def request(self, message="这个怎么证明", **kwargs):
        values = dict(student_id="s", account_type="production", session_id="tab-a", message=message)
        values.update(kwargs)
        return ChatRequest(**values)

    def execute(self, route):
        def executor(request, context, resolved, intercept, guard, progress):
            self.calls.append((request, context))
            halted = intercept(route, context)
            if halted is not None: return halted
            guard()
            return {"reply": "完成解释", "answer_status": "answered", "step_advanced": False}
        return executor

    def clarify(self, **kwargs):
        return self.service.run(self.request(**kwargs), self.execute(TaskUnderstanding(status="unknown", intent="clarify_task", missing_slots=["target"])))

    def count(self, model):
        with self.factory() as session: return session.scalar(select(func.count()).select_from(model))

    def test_pending_survives_repository_recreation_and_writes_no_learning_record(self):
        result = self.clarify(request_id="r1")
        restored = LearningTaskRepository().pending("s", "tab-a")
        self.assertEqual(restored["result"], result)
        self.assertEqual(result["answer_status"], "awaiting_clarification")
        self.assertEqual(self.count(ConversationRow), 0)
        self.assertEqual(self.memory.list_knowledge_points("s"), [])

    def test_duplicate_original_does_not_resume_or_call_model(self):
        first = self.clarify(request_id="r1")
        again = self.clarify(request_id="r1")
        self.assertEqual(first, again); self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.count(TaskRequestRow), 1)

    def test_request_id_cannot_be_reused_for_new_input(self):
        self.clarify(request_id="r1")
        result = self.clarify(message="换个问题", request_id="r1")
        self.assertEqual(result["answer_status"], "request_conflict"); self.assertEqual(len(self.calls), 1)

    def test_reply_restores_original_question_and_completes(self):
        first = self.clarify(request_id="r1")
        result = self.service.run(self.request("讲定理7.2", request_id="r2"), self.execute(TaskUnderstanding()))
        self.assertEqual(result["task_id"], first["task_id"])
        self.assertIn("这个怎么证明", self.calls[-1][0].message)
        self.assertIn("讲定理7.2", self.calls[-1][0].message)
        self.assertIsNone(self.repo.pending("s", "tab-a"))
        self.assertEqual(self.repo.get("s", "tab-a", first["task_id"])["status"], "completed")

    def test_option_index_restores_only_selected_resource(self):
        first = self.clarify(request_id="r1", reader_location={"chapter_id": 7, "section_id": 1})
        result = self.service.run(self.request("第一个", request_id="r2"), self.execute(TaskUnderstanding()))
        self.assertEqual(result["task_id"], first["task_id"])
        self.assertEqual(self.calls[-1][0].reader_location.chapter_id, 7)
        self.assertIn("明确对象", self.calls[-1][0].message)

    def test_invalid_option_never_calls_executor(self):
        first = self.clarify(request_id="r1")
        result = self.service.run(self.request("第二个", task_id=first["task_id"], task_revision=first["task_revision"], request_id="r2"), self.execute(TaskUnderstanding()))
        self.assertEqual(result["answer_status"], "invalid_option"); self.assertEqual(len(self.calls), 1)

    def test_other_session_cannot_read_resume_or_cancel(self):
        first = self.clarify(request_id="r1")
        self.assertIsNone(self.repo.pending("s", "tab-b"))
        for sid, student in (("tab-b", "s"), ("tab-a", "other")):
            with self.assertRaises(TaskConflict): self.repo.cancel(student, sid, first["task_id"], first["task_revision"])
        result = self.service.run(self.request("补充", session_id="tab-b", task_id=first["task_id"], task_revision=first["task_revision"]), self.execute(TaskUnderstanding()))
        self.assertEqual(result["answer_status"], "task_not_found")

    def test_sessions_keep_independent_pending_and_recent_context(self):
        a = self.clarify(request_id="a")
        b = self.clarify(session_id="tab-b", request_id="b")
        self.assertNotEqual(a["task_id"], b["task_id"])
        self.assertEqual(self.repo.pending("s", "tab-a")["id"], a["task_id"])
        self.assertEqual(self.calls[-1][1].history, [])

    def test_explicit_new_topic_cancels_old_pending(self):
        first = self.clarify(request_id="r1")
        result = self.service.run(self.request("我想学集合", request_id="r2"), self.execute(TaskUnderstanding()))
        self.assertNotEqual(result["task_id"], first["task_id"])
        self.assertEqual(self.repo.get("s", "tab-a", first["task_id"])["status"], "cancelled")

    def test_cancel_clears_content_and_late_reply_is_rejected(self):
        first = self.clarify(request_id="r1")
        self.repo.cancel("s", "tab-a", first["task_id"], first["task_revision"])
        result = self.service.run(self.request("补充", task_id=first["task_id"], task_revision=first["task_revision"]), self.execute(TaskUnderstanding()))
        self.assertEqual(result["answer_status"], "task_conflict")
        with self.factory() as session:
            self.assertEqual(session.scalar(select(TaskRequestRow)).result, {})
        self.assertEqual(len(self.calls), 1)

    def test_stale_revision_does_not_resume(self):
        first = self.clarify(request_id="r1")
        result = self.service.run(self.request("补充", task_id=first["task_id"], task_revision=1), self.execute(TaskUnderstanding()))
        self.assertEqual(result["answer_status"], "task_conflict"); self.assertEqual(len(self.calls), 1)

    def test_expiry_scrubs_content_and_rejects_old_request(self):
        first = self.clarify(request_id="r1")
        with self.factory.begin() as session: session.get(LearningTaskRow, first["task_id"]).expires_at = now() - dt.timedelta(seconds=1)
        result = self.clarify(request_id="r1")
        self.assertEqual(result["answer_status"], "task_expired")
        row = self.repo.get("s", "tab-a", first["task_id"])
        self.assertEqual(row["status"], "expired"); self.assertEqual(row["payload"], {})
        self.assertEqual(len(self.calls), 1)

    def test_three_ambiguous_rounds_stop_without_learning_update(self):
        self.clarify(request_id="r1"); self.clarify(message="还是那个", request_id="r2")
        result = self.clarify(message="不知道", request_id="r3")
        self.assertEqual(result["answer_status"], "clarification_limit")
        self.assertIsNone(self.repo.pending("s", "tab-a")); self.assertEqual(self.count(ConversationRow), 0)

    def test_parse_failure_is_terminal_without_learning_record(self):
        result = self.service.run(self.request(request_id="r1"), self.execute(TaskUnderstanding.failure("parse_error", "无效JSON")))
        self.assertEqual(result["answer_status"], "routing_failed")
        self.assertEqual(self.repo.get("s", "tab-a", result["task_id"])["status"], "failed")
        self.assertEqual(self.count(ConversationRow), 0)

    def test_executor_failure_releases_active_scope(self):
        def broken(request, context, resolved, intercept, guard, progress):
            intercept(TaskUnderstanding(), context); raise RuntimeError("故障注入")
        with self.assertRaises(RuntimeError): self.service.run(self.request(request_id="r1"), broken)
        with self.factory() as session:
            row = session.scalar(select(LearningTaskRow)); self.assertEqual(row.status, "failed"); self.assertIsNone(row.scope_key)

    def test_cancel_during_generation_blocks_late_memory_and_result(self):
        def executor(request, context, resolved, intercept, guard, progress):
            intercept(TaskUnderstanding(), context)
            with self.factory() as session: row = session.scalar(select(LearningTaskRow)); task_id, revision = row.id, row.revision
            self.repo.cancel("s", "tab-a", task_id, revision)
            self.memory.append_exchange("s", request.message, "迟到答案", task_guard=guard)
            return {"reply": "迟到答案"}
        result = self.service.run(self.request(request_id="r1"), executor)
        self.assertEqual(result["answer_status"], "task_conflict"); self.assertEqual(self.count(ConversationRow), 0)

    def test_forget_pending_only_point_deletes_task_and_receipts(self):
        first = self.clarify(request_id="r1")
        point = self.repo.get("s", "tab-a", first["task_id"])["knowledge_point"]
        self.memory.repo.forget_learning_point("s", point)
        self.assertEqual(self.count(LearningTaskRow), 0); self.assertEqual(self.count(TaskRequestRow), 0)
        result = self.service.run(self.request("补充", task_id=first["task_id"], task_revision=first["task_revision"]), self.execute(TaskUnderstanding()))
        self.assertEqual(result["answer_status"], "task_not_found"); self.assertEqual(len(self.calls), 1)

    def test_completed_request_replays_without_executor(self):
        request = self.request("解释", request_id="r1")
        first = self.service.run(request, self.execute(TaskUnderstanding()))
        second = self.service.run(request, self.execute(TaskUnderstanding()))
        self.assertEqual(first, second); self.assertEqual(len(self.calls), 1)

    def test_inflight_duplicate_returns_busy_not_executing_metadata(self):
        def executor(request, context, resolved, intercept, guard, progress):
            intercept(TaskUnderstanding(), context)
            duplicate = self.service.run(request, self.execute(TaskUnderstanding()))
            self.assertEqual(duplicate["answer_status"], "task_busy")
            self.assertTrue(duplicate["reply"])
            return {"reply": "完成"}
        self.service.run(self.request(request_id="r1"), executor)
        self.assertEqual(self.calls, [])

    def test_competing_supplements_only_one_can_claim_revision(self):
        from concurrent.futures import ThreadPoolExecutor
        first = self.clarify(request_id="r1")
        row = self.repo.get("s", "tab-a", first["task_id"])
        def claim(key):
            try:
                self.repo.claim(student_id="s", session_id="tab-a", request_id=key, payload={"message": key},
                    point=row["knowledge_point"], epoch=row["epoch"], memory_repo=self.memory.repo,
                    task_id=row["id"], revision=row["revision"])
                return "claimed"
            except TaskConflict as error: return error.code
        with ThreadPoolExecutor(max_workers=2) as pool: outcomes = list(pool.map(claim, ["r2", "r3"]))
        self.assertCountEqual(outcomes, ["claimed", "task_conflict"])

    def test_account_delete_during_generation_does_not_recreate_or_save(self):
        def executor(request, context, resolved, intercept, guard, progress):
            intercept(TaskUnderstanding(), context)
            self.memory.repo.delete_student("s")
            self.memory.append_exchange("s", request.message, "晚到解释", task_guard=guard)
            return {"reply": "晚到解释"}
        result = self.service.run(self.request(request_id="r1"), executor)
        self.assertEqual(result["answer_status"], "task_not_found")
        self.assertIsNone(self.memory.repo.get_account_type("s"))
        self.assertEqual(self.count(TaskRequestRow), 0); self.assertEqual(self.count(ConversationRow), 0)

    def test_additive_initialization_preserves_old_learning_state(self):
        from models.student_state import StudentState
        self.memory.save_state("s", "集合", StudentState(student_id="s", current_concept="集合", mastery=.7))
        Base.metadata.create_all(self.engine); Base.metadata.create_all(self.engine)
        self.assertEqual(self.memory.get_state("s", "集合").mastery, .7)

    def test_second_option_selects_prior_object_not_current_page(self):
        for key, section in (("old", 1), ("new", 2)):
            self.service.run(self.request("解释本小节", request_id=key, reader_location={"chapter_id": 7, "section_id": section}), self.execute(TaskUnderstanding()))
        first = self.clarify(request_id="clarify")
        self.assertEqual(len(first["clarification"]["options"]), 2)
        result = self.service.run(self.request("第二个", request_id="resume"), self.execute(TaskUnderstanding()))
        self.assertEqual(result["task_id"], first["task_id"])
        self.assertEqual(self.calls[-1][0].reader_location.section_id, 1)
        self.assertIn("这个怎么证明", self.calls[-1][0].message)

    def test_negation_removes_old_resource_before_understanding(self):
        self.clarify(request_id="r1", reader_location={"chapter_id": 7, "section_id": 1})
        self.service.run(self.request("不是这个，解释集合定义", request_id="r2"), self.execute(TaskUnderstanding()))
        self.assertIsNone(self.calls[-1][0].reader_location)

    def test_cancel_guard_prevents_mastery_and_evidence_commit(self):
        from models.student_state import StudentState
        from models.lesson_plan import LessonPlan, LessonStep
        from memory.evidence_policy import EvidenceDecision
        from database.models import EvidenceRow, LearningEventRow, MemoryRevisionRow
        first = self.clarify(request_id="r1")
        row = self.repo.get("s", "tab-a", first["task_id"])
        self.repo.cancel("s", "tab-a", row["id"], row["revision"])
        point = row["knowledge_point"]
        token = self.memory.repo.memory_token("s", point)
        def guard(): self.repo.guard("s", "tab-a", row["id"], row["revision"], self.memory.repo)
        with self.assertRaises(TaskConflict):
            self.memory.commit_learning_turn(student_id="s", point=point, event_id="late",
                expected_token=token, message="答案", reply="旧回答",
                state=StudentState(student_id="s", current_concept=point, mastery=.9),
                lesson_plan=LessonPlan(goal=point, steps=[LessonStep(step_id="S1", objective="理解")], current_step="S1"),
                decision=EvidenceDecision(True, True, "独立作答"), evidence=[], hypotheses=[],
                strategy="worked_example", success=None, instructional_move="explain", task_guard=guard)
        self.assertEqual(self.memory.repo.memory_token("s", point), token)
        for model in (EvidenceRow, LearningEventRow, MemoryRevisionRow, ConversationRow): self.assertEqual(self.count(model), 0)

    def test_replaying_initial_request_after_resume_returns_latest_result(self):
        request = self.request(request_id="r1")
        self.service.run(request, self.execute(TaskUnderstanding(status="unknown", intent="clarify_task", missing_slots=["target"])))
        completed = self.service.run(self.request("解释定理7.2", request_id="r2"), self.execute(TaskUnderstanding()))
        replayed = self.service.run(request, self.execute(TaskUnderstanding()))
        self.assertEqual(replayed, completed); self.assertEqual(len(self.calls), 2)

    def test_explicit_expired_resume_has_expired_status(self):
        first = self.clarify(request_id="r1")
        with self.factory.begin() as session: session.get(LearningTaskRow, first["task_id"]).expires_at = now() - dt.timedelta(seconds=1)
        result = self.service.run(self.request("补充", task_id=first["task_id"], task_revision=first["task_revision"], request_id="r2"), self.execute(TaskUnderstanding()))
        self.assertEqual(result["answer_status"], "task_expired"); self.assertEqual(len(self.calls), 1)

    def test_selected_new_object_rebinds_deletion_scope(self):
        first = self.clarify(request_id="r1", learning_goal="集合")
        completed = self.service.run(self.request("解释这一节", request_id="r2", reader_location={"chapter_id": 7, "section_id": 1}), self.execute(TaskUnderstanding()))
        row = self.repo.get("s", "tab-a", first["task_id"])
        self.assertEqual(row["knowledge_point"], self.calls[-1][1].knowledge_point)
        self.assertNotEqual(row["knowledge_point"], "集合")
        self.memory.repo.forget_learning_point("s", row["knowledge_point"])
        with self.assertRaises(TaskConflict): self.repo.get("s", "tab-a", first["task_id"])

    def test_pending_restores_in_new_python_process(self):
        import subprocess
        import sys
        import json
        first = self.clarify(request_id="restart")
        code = "import os,json;os.environ['DATABASE_URL']='sqlite:///:memory:';os.environ['COURSE_DATABASE_URL']=" + repr(str(self.engine.url)) + ";os.environ['TUTOR_COURSE']='experimental-psychology-3';from database.learning_tasks import LearningTaskRepository;print(json.dumps(LearningTaskRepository().pending('s','tab-a')['result'],ensure_ascii=False))"
        restored = subprocess.run([sys.executable, "-X", "utf8", "-c", code], capture_output=True, text=True, encoding="utf-8", timeout=20)
        self.assertEqual(restored.returncode, 0, restored.stderr)
        self.assertEqual(json.loads(restored.stdout), first)


if __name__ == "__main__": unittest.main()
