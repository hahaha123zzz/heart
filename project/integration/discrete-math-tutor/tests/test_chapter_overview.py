"""章节导学：目录包、输出协议校验和一次性处理器。"""
import copy
import os
import unittest
from unittest.mock import Mock, patch

from agents.chapter_overview import (
    ChapterPackage, ChapterSection, build_chapter_package, run_chapter_overview,
    validate_overview,
)
from agents.input_understanding.adapters import final_summary
from llm.client import LLMJSONError
from models.chat_request import ChatRequest
from models.input_understanding import GroundedTurn, InputEnvelope, ContextHeader, TaskFrame
from models.learning_response import LearningResponse
from models.task_context import TaskContext
from tests.test_q5_learning import Q5TestBase

MESSAGE = "我想学习第一章的主要内容"


def context_for(kind="chapter_overview", section_id=None, *, constraints=None,
                message=None):
    scope = "chapter" if kind == "chapter_overview" else "section"
    message = message or (MESSAGE if kind == "chapter_overview" else "第一章第一节讲什么")
    context = TaskContext(student_id="s", session_id="x", message=message, input_mode="active",
                          turn_route={"kind": kind, "scope": scope, "chapter_id": 1,
                                      "section_id": section_id,
                                      "constraints": list(constraints or []),
                                      "target_id": f"chapter:1" if section_id is None else "section:1:1"})
    return context, ChatRequest(student_id="s", session_id="x", request_id="r", message=message)


def valid_payload(package):
    return {
        "roadmap": "本章是实验心理学概论[1]。",
        "sections": [{"section_id": section.section_id, "question": f"{section.title}的核心问题[1]"}
                     for section in package.sections],
        "order": "先研究对象，再发展史，再实验程序，最后伦理[1]。",
        "first_concept": "实验心理学用实验方法研究心理现象[1]。",
        "next_action": "先从第一节开始。",
    }


class FakeLLM:
    def __init__(self, *payloads):
        self.payloads = list(payloads)
        self.calls = []

    def chat_json(self, messages, **kwargs):
        self.calls.append(messages)
        payload = self.payloads.pop(0) if len(self.payloads) > 1 else self.payloads[0]
        if isinstance(payload, Exception):
            raise payload
        return copy.deepcopy(payload)


class PackageTests(unittest.TestCase):
    def test_package_uses_course_outline(self):
        package = build_chapter_package(1)
        self.assertEqual(package.chapter_title, "实验心理学概论")
        self.assertEqual([section.title for section in package.sections], [
            "第一节 实验心理学的研究对象",
            "第二节 实验心理学的产生与发展",
            "第三节 心理学实验的程序",
            "第四节 心理学实验中的伦理问题",
        ])
        self.assertTrue(all(section.first_target for section in package.sections))

    def test_package_sources_stay_in_chapter(self):
        package = build_chapter_package(1)
        self.assertTrue(package.sources)
        self.assertTrue(all(source["chapter_id"] == 1 for source in package.sources))
        self.assertEqual([source["index"] for source in package.sources],
                         list(range(1, len(package.sources) + 1)))
        self.assertIn("实验心理学概论", package.query)

    def test_unknown_chapter_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown_chapter"):
            build_chapter_package(99)


class ValidatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = build_chapter_package(1)

    def test_valid_payload_passes(self):
        ok, errors = validate_overview(valid_payload(self.package), self.package)
        self.assertTrue(ok, errors)

    def test_validator_rejects_wrong_chapter_title(self):
        payload = valid_payload(self.package)
        payload["roadmap"] = "第一章的标题是心理学的实验设计和数据处理[1]"
        ok, errors = validate_overview(payload, self.package)
        self.assertFalse(ok)
        self.assertTrue(any("chapter_title" in error for error in errors))

    def test_validator_rejects_missing_section(self):
        payload = valid_payload(self.package)
        payload["sections"] = payload["sections"][:1]
        ok, errors = validate_overview(payload, self.package)
        self.assertFalse(ok)
        self.assertTrue(any("section_coverage" in error for error in errors))

    def test_validator_accepts_explicit_omitted_section(self):
        payload = valid_payload(self.package)
        payload["sections"] = payload["sections"][:1]
        payload["omitted_sections"] = [section.section_id for section in self.package.sections[1:]]
        ok, errors = validate_overview(payload, self.package)
        self.assertTrue(ok, errors)

    def test_validator_rejects_mastery_claim(self):
        payload = valid_payload(self.package)
        payload["first_concept"] = "你已经掌握了本章内容[1]"
        ok, errors = validate_overview(payload, self.package)
        self.assertFalse(ok)
        self.assertTrue(any("mastery_claim" in error for error in errors))

    def test_validator_rejects_unbound_citation(self):
        payload = valid_payload(self.package)
        payload["roadmap"] = "这一章讲实验设计[9]"
        ok, errors = validate_overview(payload, self.package)
        self.assertFalse(ok)
        self.assertTrue(any("citation_unbound" in error for error in errors))

    def test_validator_rejects_unknown_section_id(self):
        payload = valid_payload(self.package)
        payload["sections"].append({"section_id": 99, "question": "不存在的节[1]"})
        ok, errors = validate_overview(payload, self.package)
        self.assertFalse(ok)
        self.assertTrue(any("section_unknown" in error for error in errors))

    def test_validator_rejects_uncited_fabricated_fact(self):
        payload = valid_payload(self.package)
        payload["roadmap"] = "冯特于1879年建立了第一个心理学实验室。本章是实验心理学概论[1]。"
        ok, errors = validate_overview(payload, self.package)
        self.assertFalse(ok)
        self.assertTrue(any("uncited_fact" in error for error in errors))

    def test_validator_rejects_second_question_outside_next_action(self):
        payload = valid_payload(self.package)
        payload["roadmap"] = "本章是实验心理学概论[1]。你知道研究方法吗？"
        ok, errors = validate_overview(payload, self.package)
        self.assertFalse(ok)
        self.assertTrue(any("question_limit" in error for error in errors))

    def test_no_sources_allows_structure_only_without_first_concept(self):
        package = ChapterPackage(1, "实验心理学概论",
                                 (ChapterSection(1, "第一节 实验心理学的研究对象", "实验心理学的核心", "a.txt"),),
                                 (), "实验心理学概论 第一节 实验心理学的研究对象")
        payload = {"roadmap": "本章是实验心理学概论。",
                   "sections": [{"section_id": 1, "question": "第一节 实验心理学的研究对象的核心问题"}],
                   "order": "先看第一节。", "first_concept": "", "next_action": "从第一节开始。"}
        ok, errors = validate_overview(payload, package, require_citations=False)
        self.assertTrue(ok, errors)
        payload["first_concept"] = "实验心理学用实验方法研究心理现象。"
        ok, errors = validate_overview(payload, package, require_citations=False)
        self.assertFalse(ok)
        self.assertTrue(any("first_concept_without_sources" in error for error in errors))


class HandlerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = build_chapter_package(1)

    def test_exact_phrase_returns_grounded_chapter_overview(self):
        llm = FakeLLM(valid_payload(self.package))
        context, request = context_for()
        result = run_chapter_overview(context, request, llm, package=self.package)
        self.assertEqual(result["answer_status"], "answered")
        self.assertIn("实验心理学概论", result["reply"])
        for title in ("第一节", "第二节", "第三节", "第四节"):
            self.assertIn(title, result["reply"])
        self.assertTrue(result["chapter_overview"]["coverage_ok"])
        self.assertTrue(result["chapter_overview"]["content_ok"])
        self.assertEqual(result["chapter_overview"]["chapter_id"], 1)
        self.assertEqual(result["course_navigation"]["status"], "ready")
        self.assertEqual(result["course_navigation"]["mode"], "overview")
        self.assertFalse(result.get("teaching", {}).get("formal_mastery", False))
        self.assertFalse(result["step_advanced"])
        self.assertEqual(len(llm.calls), 1)
        LearningResponse.model_validate(result["learning_response"])
        self.assertTrue(result["sources"])

    def test_missing_section_is_not_answered(self):
        payload = valid_payload(self.package)
        payload["sections"] = payload["sections"][:3]
        llm = FakeLLM(payload)
        context, request = context_for()
        result = run_chapter_overview(context, request, llm, package=self.package)
        self.assertEqual(result["answer_status"], "partial")
        self.assertFalse(result["chapter_overview"]["content_ok"])
        self.assertIn("本次没有可取正文", result["reply"])
        self.assertEqual(len(llm.calls), 2)

    def test_fabricated_fact_after_retry_degrades_without_publishing_it(self):
        payload = valid_payload(self.package)
        payload["roadmap"] = "冯特于1879年建立了世界上第一个心理学实验室。"
        llm = FakeLLM(payload, payload)
        context, request = context_for()
        result = run_chapter_overview(context, request, llm, package=self.package)
        self.assertEqual(result["answer_status"], "partial")
        self.assertFalse(result["chapter_overview"]["content_ok"])
        self.assertNotIn("冯特于1879年", result["reply"])
        self.assertEqual(len(llm.calls), 2)

    def test_overview_repairs_once_then_publishes(self):
        broken = valid_payload(self.package)
        broken["sections"] = broken["sections"][:1]
        llm = FakeLLM(broken, valid_payload(self.package))
        context, request = context_for()
        result = run_chapter_overview(context, request, llm, package=self.package)
        self.assertEqual(result["answer_status"], "answered")
        self.assertEqual(len(llm.calls), 2)
        self.assertIn("section_coverage", str(llm.calls[1]))

    def test_llm_error_is_repaired_once_then_publishes(self):
        llm = FakeLLM(LLMJSONError("invalid json"), valid_payload(self.package))
        context, request = context_for()
        result = run_chapter_overview(context, request, llm, package=self.package)
        self.assertEqual(result["answer_status"], "answered")
        self.assertEqual(len(llm.calls), 2)
        self.assertIn("model_output_invalid", str(llm.calls[1]))

    def test_llm_error_twice_degrades_to_structure_only(self):
        llm = FakeLLM(LLMJSONError("invalid json"))
        context, request = context_for()
        result = run_chapter_overview(context, request, llm, package=self.package)
        self.assertEqual(result["answer_status"], "partial")
        self.assertTrue(result["chapter_overview"]["coverage_ok"])
        self.assertFalse(result["chapter_overview"]["content_ok"])
        self.assertEqual(result["course_navigation"]["mode"], "overview")
        self.assertIn("第一节", result["reply"])
        self.assertIn("第四节", result["reply"])
        self.assertNotRegex(result["reply"], r"\[\d+\]")
        self.assertTrue(result["sources"])
        self.assertEqual(len(llm.calls), 2)

    def test_no_questions_constraint_renders_statements(self):
        from agents.input_understanding.service import understand
        from models.task_context import apply_route
        payload = valid_payload(self.package)
        payload["next_action"] = "要不要从第一节开始？"
        message = "不要出题，只讲第一章主要内容"
        context = TaskContext(student_id="s", session_id="x", message=message, input_mode="active")
        request = ChatRequest(student_id="s", session_id="x", request_id="r", message=message)
        context.input_understanding = understand(context, request)
        apply_route(context, context.input_understanding.route)
        self.assertIn("no_questions", context.turn_route["constraints"])
        result = run_chapter_overview(context, request, FakeLLM(payload), package=self.package)
        self.assertEqual(result["answer_status"], "answered")
        self.assertNotIn("？", result["reply"])
        self.assertNotIn("?", result["reply"])
        self.assertIn("下一步：", result["reply"])

    def test_overview_cursor_continues_to_the_next_target(self):
        context, request = context_for()
        result = run_chapter_overview(context, request, FakeLLM(valid_payload(self.package)),
                                      package=self.package)
        cursor = result["course_navigation"]
        self.assertTrue(cursor["id"])
        self.assertTrue(cursor["version"])
        self.assertEqual(cursor["section_id"], 1)
        self.assertEqual(cursor["status"], "ready")
        from knowledge.course_navigation import resolve
        following = resolve("下一部分", cursor=cursor)
        self.assertEqual(following["status"], "ready")
        self.assertEqual(following["chapter_id"], 1)

    def test_no_sources_returns_structure_only_partial(self):
        package = ChapterPackage(1, "实验心理学概论",
                                 (ChapterSection(1, "第一节 实验心理学的研究对象", "实验心理学的核心", None),
                                  ChapterSection(2, "第二节 实验心理学的产生与发展", "发展史", None)),
                                 (), "实验心理学概论 第一节 实验心理学的研究对象 第二节 实验心理学的产生与发展")
        llm = FakeLLM(valid_payload(package))
        context, request = context_for()
        result = run_chapter_overview(context, request, llm, package=package)
        self.assertEqual(result["answer_status"], "partial")
        self.assertTrue(result["chapter_overview"]["coverage_ok"])
        self.assertFalse(result["chapter_overview"]["content_ok"])
        self.assertIn("第一节", result["reply"])
        self.assertIn("第二节", result["reply"])
        self.assertNotRegex(result["reply"], r"\[\d+\]")
        self.assertEqual(llm.calls, [])
        self.assertEqual(result["sources"], [])

    def test_unknown_chapter_asks_for_a_chapter(self):
        context = TaskContext(student_id="s", session_id="x", message=MESSAGE, input_mode="active",
                              turn_route={"kind": "chapter_overview", "scope": "chapter",
                                          "chapter_id": 99, "target_id": "chapter:99"})
        request = ChatRequest(student_id="s", session_id="x", request_id="r", message=MESSAGE)
        result = run_chapter_overview(context, request, FakeLLM(valid_payload(self.package)), package=None)
        self.assertEqual(result["answer_status"], "clarify")

    def test_section_overview_only_covers_that_section(self):
        payload = valid_payload(self.package)
        payload["sections"] = payload["sections"][:1]
        llm = FakeLLM(payload)
        context, request = context_for("section_overview", section_id=1)
        result = run_chapter_overview(context, request, llm, package=self.package)
        self.assertEqual(result["answer_status"], "answered")
        self.assertEqual(result["chapter_overview"]["section_ids"], [1])


class SummaryTests(unittest.TestCase):
    def turn(self):
        message = MESSAGE
        return GroundedTurn(
            envelope=InputEnvelope(request_id="r", raw_text=message, normalized_text=message,
                                   source_positions=list(range(len(message)))),
            context=ContextHeader(student_id="s", session_id="x", course_id="experimental-psychology-3"),
            tasks=[TaskFrame(task_frame_id="f1", action="chapter_overview")])

    def test_partial_overview_does_not_complete_the_frame(self):
        context = TaskContext(student_id="s", session_id="x", message=MESSAGE, input_mode="active",
                              input_understanding=self.turn())
        summary = final_summary(context, {"answer_status": "partial",
                                          "chapter_overview": {"coverage_ok": True, "content_ok": False}})
        self.assertEqual(summary["states"], ["pending"])

    def test_grounded_overview_completes_the_frame(self):
        context = TaskContext(student_id="s", session_id="x", message=MESSAGE, input_mode="active",
                              input_understanding=self.turn())
        summary = final_summary(context, {"answer_status": "answered",
                                          "chapter_overview": {"coverage_ok": True, "content_ok": True}})
        self.assertEqual(summary["states"], ["completed"])


class TaskServiceOverviewTests(Q5TestBase):
    """Drive the real task service so the branch order is verified, not just the handler."""

    def setUp(self):
        super().setUp()
        import database.learning_tasks  # noqa: F401
        from agents.task_service import TaskService
        from database.learning_tasks import LearningTaskRepository
        from memory.memory_manager import MemoryManager
        self.memory = MemoryManager()
        self.memory.ensure_student("s", account_type="test")
        self.repository = LearningTaskRepository()
        self.package = build_chapter_package(1)
        self.executed = []
        tutor = Mock()
        tutor.memory = self.memory
        tutor.llm = Mock()
        tutor.llm.chat_json.return_value = valid_payload(self.package)
        policy = Mock()
        policy.enabled.return_value = True
        policy.can_clarify.return_value = True
        policy.context = True
        self.service = TaskService(tutor, repository=self.repository, policy=policy)

    def executor(self, request, context, resolved, intercept, guard, progress):
        self.executed.append(request.message)
        return {"reply": "普通回答", "answer_status": "answered", "step_advanced": False}

    def run_turn(self, request_id="overview-request"):
        return self.service.run(ChatRequest(student_id="s", session_id="overview-session",
            request_id=request_id, message="我想学习第一章的主要内容"), self.executor)

    def test_route_is_served_before_q5_and_saved_by_save_answer(self):
        with patch.dict(os.environ, {"INPUT_UNDERSTANDING_MODE": "active",
                                     "Q5_LEARNING_ENABLED": "1"}), \
             patch("agents.q5_runtime.Q5Runtime.propose_chapter_plan",
                   side_effect=AssertionError("Q5 must not run")), \
             patch("agents.q5_runtime.Q5Runtime.propose_session",
                   side_effect=AssertionError("Q5 must not run")):
            result = self.run_turn()
            again = self.run_turn()

        self.assertEqual(result["answer_status"], "answered")
        self.assertEqual(result["result_type"], "chapter_overview")
        self.assertTrue(result["chapter_overview"]["coverage_ok"])
        self.assertTrue(result["chapter_overview"]["content_ok"])
        self.assertEqual(result["course_navigation"]["status"], "ready")
        self.assertEqual(result["course_navigation"]["mode"], "overview")
        self.assertEqual(self.executed, [])
        row = self.repository.get("s", "overview-session", result["task_id"])
        self.assertEqual(row["status"], "completed")
        from knowledge.course_navigation import previous_cursor, resolve
        restored = previous_cursor(self.repository.navigation_recent("s", "overview-session"),
                                   self.memory, "s")
        self.assertEqual(restored["id"], result["course_navigation"]["id"])
        self.assertEqual(resolve("下一部分", cursor=restored)["status"], "ready")
        self.assertEqual(again["reply"], result["reply"])
        self.assertEqual(again["task_id"], result["task_id"])
        self.assertEqual(self.executed, [])


if __name__ == "__main__":
    unittest.main()
