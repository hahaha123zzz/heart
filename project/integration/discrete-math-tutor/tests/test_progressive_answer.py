"""隔离 SQLite 验证先落文字、后补图、删除和幂等边界。"""
import unittest
from unittest.mock import Mock, patch
from tests import test_clarification_tasks as fixtures
from models.task_understanding import TaskUnderstanding
from visualization.on_demand import build_guide


class ProgressiveAnswerTests(unittest.TestCase):
    setUp = fixtures.ClarificationTests.setUp
    tearDown = fixtures.ClarificationTests.tearDown
    request = fixtures.ClarificationTests.request

    def execute(self, request, context, resolved, intercept, guard, progress):
        intercept(TaskUnderstanding(), context)
        references=[{'source_index':0,'evidence':{'evidence_id':'stable-id','quote':'完整原文',
            'selections':[{'rects':[{'page':19}]},{'rects':[{'page':20}]}]}}]
        cid = self.memory.append_exchange("s", request.message, "已核验文字 [1]",
            selection_ref={"textbook_sources": ["教材"], "section_title": context.knowledge_point,'pdf_references':references}, expected_point=context.knowledge_point, task_guard=guard)
        return {"answer_status": "answered", "reply": "已核验文字 [1]", "conversation_id": cid,'pdf_references':references}

    def history(self):
        return self.memory.repo.get_conversation_with_figures("s")

    def test_text_is_durable_before_guide_and_replay_does_not_repeat(self):
        order = []
        def ready(result):
            self.assertEqual(self.history()[-1]["content"], result["reply"])
            self.assertNotIn("guided_visualization", self.history()[-1]["selection_ref"])
            self.assertEqual(self.history()[-1]['selection_ref']['pdf_references'],result['pdf_references'])
            order.append("answer")
        def build():
            self.assertEqual(order, ["answer"])
            order.append("guide")
            return {"id": "isolated-deck"}
        request = self.request(request_id="progressive-1")
        result = self.service.run(request, self.execute, visualization_jobs=[build], answer_ready=ready)
        self.assertEqual(result["visualization_status"], "ready")
        self.assertEqual(self.history()[-1]["selection_ref"]["guided_visualization"], {"id": "isolated-deck"})
        self.assertEqual(self.history()[-1]["selection_ref"]["textbook_sources"], ["教材"])
        self.assertEqual(self.history()[-1]['selection_ref']['pdf_references'],result['pdf_references'])
        again = self.service.run(request, Mock(side_effect=AssertionError("重复生成")), visualization_jobs=[build], answer_ready=ready)
        self.assertEqual(again, result)
        self.assertEqual(order, ["answer", "guide"])
        self.assertEqual(len(self.history()), 2)

    def test_optional_failure_keeps_answer_and_completes_receipt(self):
        with self.assertLogs("agents.task_service", level="ERROR"):
            result = self.service.run(self.request(request_id="fail-guide"), self.execute,
                visualization_jobs=[Mock(side_effect=RuntimeError("故障注入"))])
        self.assertEqual(result["answer_status"], "answered")
        self.assertEqual(result["visualization_status"], "unavailable")
        self.assertEqual(self.history()[-1]["content"], result["reply"])
        self.assertEqual(self.repo.get("s", "tab-a", result["task_id"])["status"], "completed")

    def test_delete_while_building_never_recreates_text_or_guide(self):
        def build():
            # 当前任务仍在 executing；直接取当前回答所属知识点。
            with self.factory() as session:
                row = session.query(fixtures.LearningTaskRow).first()
                point = row.knowledge_point
            self.memory.repo.forget_learning_point("s", point)
            return {"id": "late"}
        result = self.service.run(self.request(request_id="delete-guide"), self.execute, visualization_jobs=[build])
        self.assertIn(result["answer_status"], ("task_not_found", "memory_deleted"))
        self.assertEqual(self.history(), [])

    def test_attachment_cannot_cross_student_or_recreate_deleted_row(self):
        self.memory.ensure_student("other")
        cid = self.memory.append_exchange("s", "问题", "回答")
        self.assertFalse(self.memory.repo.attach_guide("other", cid, {"id": "wrong-owner"}))
        self.assertFalse(self.memory.repo.attach_guide("s", cid + 100, {"id": "missing"}))
        self.assertIsNone(self.history()[-1]["selection_ref"])

    def test_invalid_visual_selector_records_the_failed_stage(self):
        from types import SimpleNamespace
        from knowledge.textbook import TextbookChunk
        from visualization.on_demand import generate_guide
        source=TextbookChunk("教材", "实验设计", "比较处理水平", frozenset())
        llm=SimpleNamespace(chat_json=Mock(return_value={"templates": ["unknown-template"]}))
        execution=SimpleNamespace(hint_only=False,learning_intents=["compare"])
        with patch.dict("os.environ", {"VISUALIZATION_ON_DEMAND": "1"}), self.assertLogs("visualization.on_demand", level="INFO") as logs:
            result=generate_guide(llm,"比较实验设计","核验后的文字",[source],execution,student_id="isolated",turn_id="invalid-selector")
        self.assertIsNone(result)
        self.assertTrue(any("stage=visual-select" in line and "error=ValueError" in line for line in logs.output))
        llm.chat_json.assert_called_once()

    def test_deferred_builder_does_no_model_work_before_invocation(self):
        jobs = []
        with patch("visualization.on_demand.PSYCHOLOGY", True), patch("visualization.on_demand.generate_guide", return_value={"id": "built"}) as generate:
            self.assertIsNone(build_guide(Mock(), "问题", "核验后的文字", [], Mock(), deferred=jobs, turn_id="t1"))
            generate.assert_not_called()
            self.assertEqual(jobs[0](), {"id": "built"})
            generate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
