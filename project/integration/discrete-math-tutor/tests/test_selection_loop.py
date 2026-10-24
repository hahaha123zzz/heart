"""PDF text adapter: real coordinate evidence, hard scope and shared loop."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import fitz

from agents.selection_loop import SelectionLoopInput, descriptor, recover_selection
from agents.q3_navigation import LearningTarget
from agents.agent_loop_service import run_agent_loop_turn
from agents.adaptive_tutoring import TeachingTurn
from knowledge.pdf_reader import PDFSelection, resolve_selection
from knowledge.grounded_citations import EvidenceBundle
from knowledge.lightrag.retrieval import as_textbook_chunk
from models.chat_request import ChatRequest
from models.task_context import TaskContext, TaskObject
from llm.client import ChatToolResult
from tests.test_q3_q4_integration import ScriptedLLM, FakeMemory, tool_round


class SelectionLoopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "fixture.pdf"
        with fitz.open() as pdf:
            page = pdf.new_page(width=600, height=800)
            page.insert_text((50, 100), "The independent variable is manipulated by the researcher.", fontsize=12)
            page.insert_text((50, 125), "The dependent variable is the measured response.", fontsize=12)
            page.insert_text((50, 500), "FAR AWAY OUT OF SCOPE: unrelated textbook content.", fontsize=12)
            pdf.save(self.path)
        self.record = {"document_id": "chapter-02", "chapter_id": 2,
            "version": hashlib.sha256(self.path.read_bytes()).hexdigest(), "page_count": 1,
            "source": "fixture.pdf", "sections": [{"id": 1, "title": "Variables", "page": 1, "y": 0}]}
        self.patchers = [
            patch.dict("os.environ", {"LOCAL_AGENT_LOOP_ENABLED": "1",
                "SELECTED_TEXT_AGENT_LOOP_ENABLED": "1", "ADAPTIVE_TUTORING_ENABLED": "1",
                "Q5_LEARNING_ENABLED": "0"}),
            patch("knowledge.pdf_reader.document", return_value=self.record),
            patch("knowledge.pdf_reader.pdf_path", return_value=self.path),
            patch("agents.selection_loop.document", return_value=self.record),
            patch("agents.selection_loop.pdf_path", return_value=self.path),
            patch("knowledge.grounded_citations.documents", return_value=[self.record]),
            patch("knowledge.grounded_citations.pdf_path", return_value=self.path),
            patch("knowledge.course_release.binding", return_value={}),
        ]
        for p in self.patchers:
            p.start()
        with fitz.open(self.path) as pdf:
            page = pdf[0]
            box = page.search_for("independent variable")[0]
            self.rect = {"page": 1, "x1": (box.x0-1)/600, "y1": (box.y0-1)/800,
                         "x2": (box.x1+1)/600, "y2": (box.y1+1)/800}
        self.selection = PDFSelection(document_id="chapter-02", version=self.record["version"],
                                      kind="text", rects=[self.rect], text="FORGED CLIENT PREVIEW")

    def tearDown(self):
        for p in reversed(self.patchers):
            p.stop()
        self.temp.cleanup()

    def context(self, message="请解释我选中的这段内容", selection=None, tutoring=None):
        selection = selection or self.selection
        scope = descriptor(selection)
        return TaskContext(student_id="s", session_id="x", message=message, knowledge_point="Variables",
            selection_scope=scope, tutoring=deepcopy(tutoring or {}),
            objects=[TaskObject(id=scope["target_id"], kind="pdf_selection", title="Variables",
                text="independent variable", chapter_id=2, section_id=1, version=selection.version)])

    def request(self, context, selection=None):
        return ChatRequest(student_id="s", session_id="x", request_id="r",
                           message=context.message, selection=selection or self.selection)

    def test_actual_text_not_client_preview_and_context_is_bounded(self):
        ctx = self.context()
        adapter = SelectionLoopInput(ctx)
        self.assertEqual(adapter.selected_text, "independent variable")
        self.assertNotIn("FORGED", json.dumps(adapter.initial_sources()))
        self.assertNotIn("FAR AWAY", json.dumps(adapter.initial_sources()))
        self.assertLessEqual(len(adapter.sources), 4)
        self.assertEqual(adapter.sources[0].location["evidence"]["selected_target"], True)
        self.assertIn("manipulated", " ".join(s.text for s in adapter.sources))
        other_preview = self.selection.model_copy(update={"text": "ANOTHER SPOOF"})
        self.assertEqual(descriptor(other_preview), descriptor(self.selection))

    def test_all_citations_publish_with_real_coordinates(self):
        adapter = SelectionLoopInput(self.context())
        rows = adapter.initial_sources()
        bundle = EvidenceBundle([as_textbook_chunk(row) for row in rows],
                                [row["location"]["evidence"] for row in rows], [])
        text = "\n".join(row["text"] + "[" + str(row["index"]) + "]" for row in rows)
        body, _, refs = bundle.publish(text)
        self.assertEqual(len(refs), len(rows))
        self.assertTrue(all(ref["evidence"]["location_status"] == "exact" for ref in refs))
        self.assertTrue(all(ref["evidence"]["selections"] for ref in refs))

    def test_retrieve_cannot_expand_to_new_target_or_global_engine(self):
        adapter = SelectionLoopInput(self.context())
        with patch("knowledge.local_rag.course_retrieval.retrieve", side_effect=AssertionError("global search")):
            result = adapter.search(target=adapter.target, query="whole textbook chapter 11", limit=10)
        self.assertEqual(result, adapter.sources)
        self.assertFalse(adapter.calls[-1]["global_expansion"])
        with self.assertRaisesRegex(ValueError, "范围"):
            adapter.search(target=LearningTarget(target_id="other", name="Other"), query="x", limit=1)

    def test_changed_file_is_rejected_at_boundary(self):
        adapter = SelectionLoopInput(self.context())
        self.path.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "变化"):
            adapter.guard()

    def test_area_selection_is_not_silently_treated_as_text(self):
        ctx = self.context()
        ctx.selection_scope = descriptor(self.selection.model_copy(update={"kind": "area"}))
        with self.assertRaises(ValueError):
            SelectionLoopInput(ctx)

    def test_hint_only_reuses_existing_task_execution_contract(self):
        adapter = SelectionLoopInput(self.context("只给提示，不要给完整答案"))
        self.assertTrue(adapter.execution.hint_only)
        self.assertTrue(adapter.execution.no_questions)
        self.assertIn("提示", adapter.instructions())

    def test_model_cannot_deny_a_selection_that_was_supplied(self):
        adapter = SelectionLoopInput(self.context())
        self.assertFalse(adapter.gate('本轮消息没有附带新的选区正文，只能解释旧内容。')[0])
        self.assertFalse(adapter.gate('本轮我能核验到的选区文字，仍然是操作性自变量这一部分，没有出现新段落的正文。')[0])
        self.assertTrue(adapter.gate('更正：我上一轮说本轮未呈现选区，这么说不对。')[0])
        self.assertTrue(adapter.gate('这个选区没有说明该实验的具体结果，不能猜测。')[0])

    def saved_row(self, ctx):
        return {"student_id": "s", "session_id": "x", "knowledge_point": "Variables", "epoch": 0,
                "context": ctx.model_dump(), "result": {"answer_status": "answered",
                    "memory_commit": {"status": "committed"}}}

    def test_explicit_followup_without_selection_recovers_only_own_scope(self):
        ctx = self.context()
        repo = Mock(); repo.memory_epoch.return_value = 0
        request = ChatRequest(student_id="s", session_id="x", message="没听懂，换个例子")
        row = self.saved_row(ctx)
        self.assertEqual(recover_selection([row], request, repo), self.selection.model_copy(update={"text": ""}))
        failed = row | {"result": {"answer_status": "quality_rejected"}}
        self.assertIsNotNone(recover_selection([row, failed], request, repo))
        for replacement in ({"session_id": "other"}, {"student_id": "other"}, {"epoch": 1}):
            self.assertIsNone(recover_selection([row | replacement], request, repo))
        for message in ("换个话题", "什么是信度", "解释信度", "介绍一下因变量", "开始新的学习"):
            self.assertIsNone(recover_selection([row], request.model_copy(update={"message": message}), repo))
        repo.memory_epoch.return_value = 1
        self.assertIsNone(recover_selection([row], request, repo))

    def test_reader_or_explicit_object_change_does_not_restore_old_selection(self):
        row = self.saved_row(self.context())
        repo = Mock(); repo.memory_epoch.return_value = 0
        request = ChatRequest(student_id="s", session_id="x", message="没听懂",
                              reader_location={"chapter_id": 3, "section_id": 1})
        self.assertIsNone(recover_selection([row], request, repo))
        request = request.model_copy(update={"reader_location": None, "learning_goal": "Other"})
        self.assertIsNone(recover_selection([row], request, repo))
        request = request.model_copy(update={"learning_goal": None, "selection": self.selection})
        self.assertIsNone(recover_selection([row], request, repo))

    def run_loop(self, ctx, model):
        return run_agent_loop_turn(
            orchestrator=SimpleNamespace(llm=model, memory=FakeMemory(), quality_checker=None),
            request=self.request(ctx), context=ctx,
            resolved=resolve_selection(self.selection), publish_gate=lambda *_: (True, ""))

    def test_selected_text_actually_runs_same_teaching_tool_and_pending_lifecycle(self):
        ctx = self.context()
        model = ScriptedLLM([
            tool_round("teaching_step", {"strategy": "explain", "summary": "解释操纵",
                "check_prompt": "What does the researcher manipulate?", "check_focus": "操纵",
                "check_expected_answer": "PRIVATE-key"}),
            ChatToolResult(text="The independent variable is manipulated[2].\nWhat does the researcher manipulate?", finish_reason="stop")])
        result = self.run_loop(ctx, model)
        self.assertEqual(result["entrypoint"], "pdf_text_selection")
        self.assertEqual(result["answer_status"], "answered")
        self.assertEqual(result["retrieval_calls"], [])
        self.assertEqual(result["teaching"]["engine_next"]["action"], "answer_pending")
        self.assertFalse(result["teaching"]["formal_mastery"])
        self.assertTrue(result["learning_interjection"])
        self.assertNotIn("PRIVATE-key", json.dumps(result))
        self.assertEqual(result["selection_ref"]["text"], "independent variable")
        # Repeated selection is context, not a request to reset the question.
        pending = result["teaching"]["pending_check"]
        follow = self.context("没听懂", tutoring=ctx.tutoring | {"source_candidates": result["sources"]})
        follow_model = ScriptedLLM([
            tool_round("teaching_step", {"strategy": "worked_example", "summary": "换个例子"}),
            ChatToolResult(text="换一个教学示例，研究者改变条件[2]。", finish_reason="stop")])
        follow_result = self.run_loop(follow, follow_model)
        self.assertEqual(follow_result["teaching"]["pending_check"], pending)

    def test_authoritative_new_selection_drops_previous_question(self):
        ctx = self.context()
        t = TeachingTurn(ctx, self.request(ctx), Mock(), target=SelectionLoopInput(ctx).target)
        from agents.adaptive_tutoring import TeachingStepTool
        from agents.tool_protocol import ToolContext
        TeachingStepTool(t).run({"strategy": "explain", "summary": "解释",
            "check_prompt": "Old question?", "check_focus": "old"},
            ToolContext(student_id="s", session_id="x", task_id="task"))
        moved = PDFSelection.model_validate(self.selection.model_dump() | {"rects": [dict(self.rect, y1=.13, y2=.17)]})
        other = self.context("请解释新选区", selection=moved, tutoring=t.state)
        adapter = SelectionLoopInput(other)
        self.assertTrue(adapter.scope_changed)
        new = TeachingTurn(other, self.request(other, moved), Mock(),
                           target=adapter.target)
        self.assertIsNone(new.progress.pending_question)

    def test_new_selection_does_not_seed_model_with_old_selection_dialogue(self):
        ctx = self.context(tutoring={'target_id':'selection:previous'})
        ctx.history = [{'role':'assistant','content':'OLD-SELECTION-MISSING-CONTENT-CLAIM'}]
        model = ScriptedLLM([
            tool_round('teaching_step',{'strategy':'explain','summary':'解释新选区'}),
            ChatToolResult(text='当前选区说明研究者操纵的变量[2]。',finish_reason='stop')])
        result = self.run_loop(ctx, model)
        self.assertEqual(result['answer_status'],'answered')
        self.assertNotIn('OLD-SELECTION-MISSING-CONTENT-CLAIM',json.dumps(model.calls[0]['messages']))


if __name__ == "__main__":
    unittest.main()
