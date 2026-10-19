"""任务对象信任边界、单次识别及API兼容的离线验证。"""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from pydantic import ValidationError

from agents.conversation_router import ConversationRouter
from agents.task_context_builder import TaskContextBuilder
from models.chat_request import ChatRequest
from models.task_context import TaskContext, TaskObject, ReaderLocation, ExerciseTarget
from llm.client import LLMClient


def context(objects=(), message="这个为什么成立？", student_id="s"):
    return TaskContext(student_id=student_id, message=message, knowledge_point="图", objects=list(objects))


def output(**changes):
    data = dict(student_move="question", move_status="", intent="continue", topic="", confidence=.9,
        reason="当前请求", needs_context=True, learning_intents=["explain"], target_refs=[],
        answer_constraints=[], missing_slots=[])
    data.update(changes)
    return data


class TaskContextTests(unittest.TestCase):
    def test_missing_location_does_not_invent_object(self):
        built = TaskContextBuilder().build(student_id="s", message="这个")
        self.assertEqual(built.objects, [])

    def test_real_section_is_resolved_by_id_not_client_title(self):
        built = TaskContextBuilder().build(student_id="s", message="解释这个小节",
            reader_location=ReaderLocation(chapter_id=7, section_id=1))
        self.assertEqual(built.objects[0].id, "section:7:1")
        self.assertTrue(built.objects[0].text)
        with self.assertRaises(ValueError):
            TaskContextBuilder().build(student_id="s", message="解释", reader_location=ReaderLocation(chapter_id=7, section_id=99999))

    def test_untrusted_selection_text_does_not_reach_context(self):
        from knowledge.pdf_reader import PDFSelection, document
        record = document("chapter-07")
        selection = PDFSelection(document_id="chapter-07", version=record["version"], kind="area",
            rects=[dict(page=1, x1=.1, y1=.1, x2=.2, y2=.2)], text="伪造答案999")
        resolved = {"text": "服务器读取的教材", "reference": selection.model_dump() | {
            "chapter_id": 7, "section_id": 1, "section_title": "图", "text": "服务器读取的教材"}}
        with patch("agents.task_context_builder.resolve_selection", return_value=resolved) as locate:
            built = TaskContextBuilder().build(student_id="s", message="解释", selection=selection)
        locate.assert_called_once_with(selection)
        self.assertNotIn("999", str(built.prompt_payload()))
        self.assertTrue(built.objects[0].id.startswith("selection:"))

    def test_exercise_version_and_part_are_validated_without_answers(self):
        from practice_api import catalog
        data = catalog(); question = data["questions"][0]; part = question["parts"][0]
        target = ExerciseTarget(question_id=question["id"], part_id=part["id"], version=data["version"])
        built = TaskContextBuilder().build(student_id="s", message="提示", exercise_target=target)
        self.assertEqual(built.objects[0].kind, "exercise_part")
        task = TaskContextBuilder.button_task(built, "hint")
        self.assertEqual(task.learning_intents, ["hint"])
        self.assertEqual(task.answer_constraints, ["hint_only", "no_full_answer"])
        for invalid in (target.model_copy(update={"version": "0" * 64}), target.model_copy(update={"part_id": "missing"})):
            with self.assertRaises(ValueError):
                TaskContextBuilder().build(student_id="s", message="解释", exercise_target=invalid)
        with self.assertRaises(ValueError):
            TaskContextBuilder.button_task(built, "delete_all")

    def test_prompt_budget_and_preferences_are_bounded(self):
        built = TaskContextBuilder().build(student_id="s", message="解释", history=[{"role": "user", "content": "x" * 10000}] * 20,
            known_points=["p" * 200] * 50, preferences={"answer_length": .5, "learning_pace": float("nan"), "mastery": 1})
        self.assertEqual(len(built.history), 20)
        self.assertEqual(len(built.history[0]["content"]), 4000)
        self.assertEqual(len(built.known_points), 20)
        self.assertEqual(built.preferences, {"answer_length": .5})
        self.assertNotIn("student_id", built.prompt_payload())

    def test_old_chat_request_keeps_legacy_default(self):
        request = ChatRequest(message="什么是交集")
        self.assertEqual(request.session_id, "legacy")
        self.assertIsNone(request.reader_location)
        with self.assertRaises(ValidationError):
            ChatRequest(message="解释", reader_location={"chapter_id": 7, "section_id": 1, "title": "伪造"})

    def test_model_cannot_invent_resource_or_rewrite_formula(self):
        built = context(message="A∧B什么时候为真？")
        for invalid in (output(target_refs=["other-student:secret"]), output(rewritten_query="A∨B是什么意思？"),
                        output(learning_intents=["delete_all"]), output(answer_constraints=["set_mastery"]),
                        output(learning_intents=["explain", "explain"]), output(intent="off_task", missing_slots=["target"])):
            self.assertEqual(ConversationRouter._validate_task(invalid, built).status, "parse_error")

    def test_missing_slot_with_continue_only_converges_to_clarification(self):
        built=context()
        value=output(intent='continue', missing_slots=['target'])
        result=ConversationRouter._validate_task(value,built)
        self.assertEqual(result.intent,'clarify_task');self.assertEqual(result.status,'ok')
        self.assertEqual(value['intent'],'continue')
        for invalid in (output(missing_slots=['invented']),output(missing_slots=['target'],target_refs=['foreign']),
                        output(missing_slots=['target'],learning_intents=['set_mastery'])):
            self.assertEqual(ConversationRouter._validate_task(invalid,built).status,'parse_error')

    def test_unique_object_is_preserved_with_one_model_call(self):
        obj = TaskObject(id="selection:verified", kind="pdf_selection", title="定理7.2", chapter_id=7, section_id=1)
        built = context([obj])
        llm = Mock(); llm.chat_json.return_value = output(target_refs=[obj.id], learning_intents=["proof"])
        task = ConversationRouter(llm).route(built.message, built.knowledge_point, [], [], context=built)
        self.assertEqual(task.status, "ok")
        self.assertEqual(task.target_refs, [obj.id])
        self.assertEqual(task.rewritten_query, built.message)
        self.assertEqual(llm.chat_json.call_count, 1)
        self.assertIn(obj.id, llm.chat_json.call_args.args[0][1]["content"])

    def test_same_words_can_clarify_without_an_object(self):
        built = context()
        task = ConversationRouter._validate_task(output(intent="clarify_task", missing_slots=["target"]), built)
        self.assertEqual(task.status, "ok")
        self.assertEqual(task.missing_slots, ["target"])

    def test_comparison_keeps_two_targets_and_request_order(self):
        objects = [TaskObject(id=i, kind="section", title=i, chapter_id=7, section_id=1) for i in ("a", "b")]
        built = context(objects, message="先比较，再举例")
        task = ConversationRouter._validate_task(output(target_refs=["a", "b"], learning_intents=["compare", "example"]), built)
        self.assertEqual(task.target_refs, ["a", "b"])
        self.assertEqual(task.learning_intents, ["compare", "example"])

    def test_context_cannot_be_reused_for_different_message(self):
        with self.assertRaises(ValueError):
            ConversationRouter(Mock()).route("新问题", "图", [], [], context=context())

    def test_old_mock_and_new_context_protocol_both_work(self):
        router = ConversationRouter(LLMClient(mock=True))
        self.assertEqual(router.route("我想学集合", "图", [], []).intent, "switch_topic")
        built = context(message="我想学集合")
        task = router.route(built.message, "图", [], [], context=built)
        self.assertEqual(task.status, "ok")
        self.assertEqual(task.topic, "集合")

    def test_orchestrator_rejects_other_student_context_before_route(self):
        from orchestrator import TutorOrchestrator
        tutor = TutorOrchestrator.__new__(TutorOrchestrator)
        tutor.memory = Mock(); tutor.memory.get_history.return_value = []; tutor.memory.get_active_goal.return_value = "图"
        tutor.conversation_router = Mock()
        with self.assertRaises(ValueError):
            tutor.handle_turn("s", "这个为什么成立？", task_context=context(student_id="other"))
        tutor.conversation_router.route.assert_not_called()

    def test_selected_explanation_uses_task_and_does_not_advance_state(self):
        from agents.pdf_selection_tutor import explain_selection
        from agents.context_sufficiency import EvidenceDecision
        from agents.quality_checker import QualityResult
        from models.student_state import StudentState
        from knowledge.pdf_reader import PDFSelection, document
        record = document("chapter-07")
        selection = PDFSelection(document_id="chapter-07", version=record["version"], kind="area",
            rects=[dict(page=1, x1=.1, y1=.1, x2=.2, y2=.2)])
        reference = selection.model_dump() | {"chapter_id": 7, "section_id": 1, "section_title": "图", "source": "教材", "image_refs": []}
        resolved = {"text": "已校验选区", "reference": reference, "section": {"title": "图"}, "images": [], "context": "背景"}
        tutor = Mock(); tutor.memory.get_history.return_value = []; tutor.memory.list_knowledge_points.return_value = []
        tutor.memory.read_version.return_value = ("token", 0)
        tutor.memory.get_state.return_value = StudentState(student_id="s", mastery=.6)
        tutor.conversation_router = ConversationRouter(LLMClient(mock=True))
        tutor.context_sufficiency.check.return_value = EvidenceDecision(status="sufficient", source_ids=["1"], reason="完整")
        tutor.quality_checker.check.return_value = QualityResult(passed=True)
        tutor.llm.chat.return_value = "所选内容说明图由顶点和边构成。[1]"
        with patch("agents.pdf_selection_tutor.resolve_selection", return_value=resolved) as locate, patch("agents.pdf_selection_tutor.selection_memory", return_value={"preferences": {}, "summary": "无相关记忆"}):
            result = explain_selection(tutor, "s", "解释选中内容", selection, "production")
        self.assertEqual(result["routing"]["learning_intents"], ["explain"])
        self.assertTrue(result["routing"]["target_refs"][0].startswith("selection:"))
        locate.assert_called_once()
        tutor.llm.chat.assert_called_once()
        self.assertIn("本轮任务", tutor.llm.chat.call_args.args[0][1]["content"])
        tutor.memory.append_exchange.assert_called_once()
        self.assertEqual(tutor.memory.append_exchange.call_args.kwargs["expected_epoch"], 0)
        tutor.memory.save_state.assert_not_called()
        tutor.memory.commit_learning_turn.assert_not_called()
        tutor.memory.set_active_goal.assert_not_called()

    def test_selected_topic_switch_reuses_identification(self):
        from agents.pdf_selection_tutor import explain_selection
        from knowledge.pdf_reader import PDFSelection, document
        record = document("chapter-07")
        selection = PDFSelection(document_id="chapter-07", version=record["version"], kind="area",
            rects=[dict(page=1, x1=.1, y1=.1, x2=.2, y2=.2)])
        reference = selection.model_dump() | {"chapter_id": 7, "section_id": 1, "section_title": "图"}
        resolved = {"text": "教材", "reference": reference, "section": {"title": "图"}, "images": [], "context": "背景"}
        tutor = Mock(); tutor.memory.get_history.return_value = []; tutor.memory.list_knowledge_points.return_value = []
        task = ConversationRouter._validate_task(output(intent="switch_topic", topic="集合", target_refs=[]), context(message="我想学集合"))
        tutor.conversation_router.route.return_value = task
        tutor.handle_turn.return_value = {"reply": "切换到集合"}
        with patch("agents.pdf_selection_tutor.resolve_selection", return_value=resolved):
            result = explain_selection(tutor, "s", "我想学集合", selection, "production")
        self.assertEqual(result["reply"], "切换到集合")
        self.assertEqual(tutor.conversation_router.route.call_count, 1)
        self.assertIs(tutor.handle_turn.call_args.kwargs["precomputed_routing"], task)
        tutor.memory.append_exchange.assert_not_called()


if __name__ == "__main__":
    unittest.main()
