"""Host adapter contract: real upstream policy, safe lifecycle, actual tool loop."""
from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from agents.adaptive_tutoring import (
    SCHEMA, TeachingTurn, TeachingStepTool, is_difficulty, snapshot_from_recent,
    verified_sources, redact_protocol,
)
from agents.deeptutor_learning.models import LearningProgress
from agents.deeptutor_learning.policy import learning_stage, next_objective
from agents.agent_loop_service import run_agent_loop_turn
from agents.q3_navigation import LearningTarget, StubLearningNavigator
from agents.tool_protocol import ToolContext
from llm.client import ChatToolResult
from models.chat_request import ChatRequest
from models.task_context import TaskContext
from tests.test_q3_q4_integration import ScriptedLLM, FakeMemory, tool_round

SOURCE = {"index": 1, "source_id": "e1", "document_id": "d", "version": "v",
          "text": "自变量是实验者操纵的变量，因变量是观察和测量的反应。", "page": 1,
          "location": {"evidence": {"document_version": "v", "quote": "自变量是实验者操纵的变量"}}}


def turn(message, old=None, llm=None, **extra):
    request = ChatRequest(student_id="s", session_id="x", request_id="r", message=message)
    context = TaskContext(student_id="s", session_id="x", knowledge_point="自变量", message=message,
                          tutoring=deepcopy(old or {}))
    return TeachingTurn(context, request, llm or Mock(),
                        validate_sources=extra.get("validate_sources", lambda x: deepcopy(x)))


def record(t, **extra):
    return TeachingStepTool(t).run(
        {"strategy": t.strategy, "summary": "用操纵和测量区分变量", **extra},
        ToolContext(student_id="s", session_id="x", task_id="task"))


def prior(*, pending=False, **extra):
    t = turn("请解释自变量")
    record(t, **({"check_prompt": "音乐影响阅读速度，操纵什么？", "check_focus": "操纵",
                  "check_expected_answer": "PRIVATE-背景音乐"} if pending else {}))
    t.commit_sources([SOURCE])
    return deepcopy(t.state) | {"source_candidates": [SOURCE]} | extra


def assessment(**extra):
    return {"move": "answer", "verdict": "correct", "student_quote": "背景音乐",
            "reason": "辨认了实验者改变的条件", "next_hint": "再辨认测量的反应", **extra}


class TeachingPolicyTests(unittest.TestCase):
    def test_reuses_actual_engine_and_not_failure_count(self):
        first = turn("我不会", prior())
        self.assertEqual(first.strategy, "worked_example")
        self.assertEqual(first.sources, [SOURCE])
        self.assertTrue(record(first).success)
        second = turn("还是不懂", first.state | {"source_candidates": [SOURCE]})
        self.assertEqual(second.strategy, "contrast")
        self.assertTrue(record(second).success)
        self.assertNotIn("struggle_count", second.state)
        self.assertFalse(is_difficulty("我不会影响结果"))
        progress = LearningProgress.model_validate(second.state["progress"])
        self.assertEqual(second.state["stage"], learning_stage(progress, second.objective.id))
        self.assertEqual(second.state["engine_next"],
                         next_objective(progress, pending_session_id="x").to_dict())

    def test_explained_never_means_mastered(self):
        t = turn("请解释自变量")
        self.assertEqual(t.state["engine_next"]["action"], "teach")
        record(t)
        self.assertEqual(t.state["stage"], "explained")
        self.assertFalse(t.state["formal_mastery"])
        self.assertFalse(t.progress.qualitative_mastery)
        self.assertFalse(t.progress.learner_mastery_overrides)

    def test_no_quiz_and_explicit_reenable(self):
        t = turn("先讲不考，不要问我", prior(pending=True))
        self.assertFalse(t.state["allow_check"])
        self.assertIsNone(t.progress.pending_question)
        self.assertFalse(record(t, check_prompt="谁是自变量？", check_focus="自变量").success)
        self.assertTrue(record(t).success)
        self.assertFalse(t.gate("你觉得呢？")[0])
        new = turn("什么是因变量", t.state)
        self.assertFalse(new.state["allow_check"])
        again = turn("可以考考我了", new.state)
        self.assertTrue(again.state["allow_check"])

    def test_teach_before_quiz_does_not_disable_future_checks(self):
        t = turn("先教再测", prior())
        self.assertTrue(t.state["allow_check"])
        self.assertEqual(t.progress.learner_profile.teaching_strategy, "teach_first")

    def test_skip_not_wrong_and_ack_preserves_original_question(self):
        model = Mock()
        skipped = turn("先跳过", prior(pending=True), model)
        self.assertIsNone(skipped.progress.pending_question)
        self.assertEqual(skipped.state["turn_move"], "check_skipped")
        for message in ("懂了", "继续", "我不会"):
            t = turn(message, prior(pending=True), model)
            self.assertIsNotNone(t.progress.pending_question)
            self.assertIsNone(t.state["assessment"])
            self.assertFalse(t.state["formal_mastery"])
        model.chat_json.assert_not_called()

    def test_feedback_uses_saved_question_and_literal_answer(self):
        model = Mock()
        model.chat_json.return_value = assessment(verdict="partial")
        t = turn("背景音乐", prior(pending=True), model)
        self.assertEqual(t.strategy, "contrast")
        self.assertFalse(t.state["assessment"]["formal_mastery"])
        self.assertIsNone(t.progress.pending_question)
        self.assertIn("音乐影响阅读速度", model.chat_json.call_args.args[0][1]["content"])
        self.assertEqual(t.state["stage"], "practiced_with_help")
        self.assertFalse(t.state["formal_mastery"])
        self.assertFalse(t.progress.qualitative_mastery)
        self.assertEqual(len(t.progress.learning_evidence), 1)
        self.assertEqual(t.state['engine_next']['action'], 'assess')
        self.assertFalse(t.progress.quiz_attempts[0].independent)

    def test_correct_formative_answer_cannot_advance_formal_gate(self):
        model = Mock()
        model.chat_json.return_value = assessment()
        t = turn("背景音乐", prior(pending=True), model)
        self.assertEqual(t.strategy, "transfer")
        self.assertFalse(t.state["formal_mastery"])
        self.assertNotEqual(t.state["engine_next"]["action"], "complete")

    def test_side_question_keeps_pending_and_original_sources(self):
        model = Mock()
        model.chat_json.return_value = assessment(move="question", verdict="unclear",
                                                  student_quote="为什么")
        before = prior(pending=True)
        t = turn("为什么是这样？", before, model)
        original = t.progress.pending_question.model_dump()
        self.assertTrue(t.interjection)
        self.assertIsNone(t.state["assessment"])
        self.assertEqual(t.sources, [])
        self.assertTrue(record(t).success)
        self.assertFalse(record(t, check_prompt="新题？", check_focus="新").success)
        t.commit_sources([SOURCE | {"source_id": "side-question"}])
        self.assertEqual(t.state["pending_sources"], before["pending_sources"])
        self.assertEqual(t.progress.pending_question.model_dump(), original)
        resumed = turn("回到刚才的题", t.state)
        self.assertEqual(resumed.progress.pending_question.model_dump(), original)
        self.assertEqual(resumed.state["turn_move"], "resume_check")

    def test_failed_or_ambiguous_feedback_never_consumes_question(self):
        for value in (RuntimeError("offline"), assessment(student_quote="没说过"),
                      assessment(move="unclear", verdict="unclear")):
            model = Mock()
            if isinstance(value, Exception):
                model.chat_json.side_effect = value
            else:
                model.chat_json.return_value = value
            t = turn("背景音乐", prior(pending=True), model)
            self.assertIsNone(t.state["assessment"])
            self.assertIsNotNone(t.progress.pending_question)
            self.assertFalse(t.progress.learning_evidence)

    def test_topic_switch_and_invalid_sources_do_not_grade_old_question(self):
        t = turn("换个知识点，什么是信度", prior(pending=True))
        self.assertIsNone(t.progress.pending_question)
        invalid = turn("我不会", prior(pending=True, allow_check=False), validate_sources=lambda _: [])
        self.assertIsNone(invalid.progress.pending_question)
        self.assertFalse(invalid.state["allow_check"])

    def test_question_identity_is_immutable_and_question_ends_reply(self):
        t = turn("我不会", prior())
        self.assertFalse(t.gate("讲解[1]")[0])
        self.assertTrue(record(t, check_prompt="谁是自变量？", check_focus="辨认操纵").success)
        qid = t.progress.pending_question.question_id
        self.assertFalse(record(t, check_prompt="另一题？", check_focus="改题").success)
        self.assertEqual(t.progress.pending_question.question_id, qid)
        self.assertTrue(t.gate("讲解[1]\n谁是自变量？")[0])
        self.assertFalse(t.gate("谁是自变量？\n答案是音乐[1]")[0])

    def test_foreign_tool_identity_cannot_mutate_state(self):
        t = turn("请解释")
        before = deepcopy(t.state)
        result = TeachingStepTool(t).run({"strategy": "explain", "summary": "外部"},
            ToolContext(student_id="other", session_id="x"))
        self.assertFalse(result.success)
        self.assertEqual(t.state, before)

    def test_private_keys_hidden_from_prompts_clients_and_protocol(self):
        t = turn("懂了", prior(pending=True))
        self.assertIn("PRIVATE-", t.state["progress"]["pending_question"]["expected_answer"])
        for value in (t.public(), t.instructions(), t.context.prompt_payload()):
            self.assertNotIn("PRIVATE-", json.dumps(value, ensure_ascii=False))
        protocol = {"messages": [{"role": "assistant", "tool_calls": [{
            "function": {"name": "teaching_step", "arguments":
                '{"check_expected_answer":"PRIVATE-KEY","summary":"ok"}'}}]}]}
        self.assertNotIn("PRIVATE-", json.dumps(redact_protocol(protocol)))
        self.assertIn("PRIVATE-", json.dumps(protocol))

    def test_state_scope_epoch_and_failed_turn(self):
        context = TaskContext(student_id="s", session_id="x", message="我不会")
        repo = Mock(); repo.memory_epoch.return_value = 0
        row = {"student_id": "s", "session_id": "x", "epoch": 0, "knowledge_point": "p",
               "context": {"tutoring": prior()},
               "result": {"answer_status": "answered", "memory_commit": {"status": "committed"}, "sources": [SOURCE]}}
        self.assertEqual(snapshot_from_recent([row], context, repo, "s")["source_candidates"], [SOURCE])
        for replacement in ({"session_id": "other"}, {"student_id": "other"}, {"epoch": 1},
                            {"result": {"answer_status": "quality_rejected"}}):
            self.assertEqual(snapshot_from_recent([row | replacement], context, repo, "s"), {})
        repo.memory_epoch.return_value = 1
        self.assertEqual(snapshot_from_recent([row], context, repo, "s"), {})

    def test_rejected_turn_does_not_erase_last_committed_state(self):
        context = TaskContext(student_id="s", session_id="x", message="继续")
        repo = Mock(); repo.memory_epoch.return_value = 0
        good = {"student_id": "s", "session_id": "x", "epoch": 0, "knowledge_point": "p",
                "context": {"tutoring": prior(pending=True)},
                "result": {"answer_status": "answered", "memory_commit": {"status": "committed"}, "sources": [SOURCE]}}
        failed = good | {"result": {"answer_status": "quality_rejected"}}
        restored = snapshot_from_recent([good, failed], context, repo, "s")
        self.assertEqual(restored['progress'], good['context']['tutoring']['progress'])

    def test_cached_source_version_and_bytes_revalidated(self):
        with patch("knowledge.pdf_reader.document", return_value={"document_id": "d", "version": "new"}), \
             patch("knowledge.course_release.binding", return_value={}):
            self.assertEqual(verified_sources([SOURCE]), [])
        import hashlib
        source = deepcopy(SOURCE)
        version = hashlib.sha256(b"pdf").hexdigest()
        source["version"] = version
        source["location"]["evidence"]["document_version"] = version
        path = Mock(); path.read_bytes.return_value = b"pdf"
        with patch("knowledge.pdf_reader.document", return_value={"document_id": "d", "version": version}), \
             patch("knowledge.pdf_reader.pdf_path", return_value=path), \
             patch("knowledge.citation_index._live_document", return_value={"folded": "自变量是实验者操纵的变量"}), \
             patch("knowledge.course_release.binding", return_value={}):
            self.assertEqual(len(verified_sources([source])), 1)
            path.read_bytes.return_value = b"changed"
            self.assertEqual(verified_sources([source]), [])


class TeachingLoopIntegrationTests(unittest.TestCase):
    @patch.dict("os.environ", {"ADAPTIVE_TUTORING_ENABLED": "1", "Q5_LEARNING_ENABLED": "0"})
    def test_restore_is_exact_saved_question_and_never_arbitrary_model_text(self):
        model = ScriptedLLM([])
        context = TaskContext(student_id="s", session_id="x", message="回到刚才的题",
                              knowledge_point="自变量", tutoring=prior(pending=True))
        request = ChatRequest(student_id="s", session_id="x", request_id="restore", message=context.message)
        with patch("agents.adaptive_tutoring.verified_sources", side_effect=lambda x: x):
            result = run_agent_loop_turn(orchestrator=SimpleNamespace(llm=model, memory=FakeMemory(), quality_checker=None),
                request=request, context=context,
                navigator=StubLearningNavigator(target=LearningTarget(target_id="p", name="自变量")),
                publish_gate=lambda *_: (_ for _ in ()).throw(AssertionError("no model gate bypass")))
        self.assertEqual(result['publication_mode'], 'saved_formative_question')
        self.assertEqual(result['reply'], '原来的小检查是：\n\n音乐影响阅读速度，操纵什么？')
        self.assertFalse(model.calls)
        self.assertEqual(result['loop_summary']['rounds'], 0)
        self.assertFalse(result['teaching']['formal_mastery'])

    @patch.dict("os.environ", {"ADAPTIVE_TUTORING_ENABLED": "1", "Q5_LEARNING_ENABLED": "0"})
    def test_actual_loop_uses_teaching_tool_and_cached_sources(self):
        model = ScriptedLLM([
            tool_round("teaching_step", {"strategy": "worked_example", "summary": "示范操纵和测量",
                        "check_prompt": "谁是自变量？", "check_focus": "辨认操纵",
                        "check_expected_answer": "PRIVATE-背景音乐"}),
            ChatToolResult(text="教学示例：改变音乐、测量阅读速度。操纵的是自变量[1]。\n谁是自变量？", finish_reason="stop")])
        context = TaskContext(student_id="s", session_id="x", message="我不会",
                              knowledge_point="自变量", tutoring=prior())
        request = ChatRequest(student_id="s", session_id="x", request_id="loop", message=context.message)
        memory = FakeMemory()
        with patch("agents.adaptive_tutoring.verified_sources", side_effect=lambda x: x):
            result = run_agent_loop_turn(orchestrator=SimpleNamespace(llm=model, memory=memory, quality_checker=None),
                request=request, context=context,
                navigator=StubLearningNavigator(target=LearningTarget(target_id="p", name="自变量")),
                publish_gate=lambda text,state: (True,""))
        self.assertEqual(result["answer_status"], "answered")
        self.assertEqual(result["loop_summary"]["tool_steps"], 1)
        self.assertEqual(result["retrieval_calls"], [])
        self.assertEqual(result["teaching"]["pending_check"]["prompt"], "谁是自变量？")
        self.assertEqual(len(memory.calls), 1)
        self.assertIn("verified_teaching_evidence", model.calls[0]["messages"][0]["content"])
        self.assertNotIn("PRIVATE-", json.dumps(result, ensure_ascii=False))
        self.assertIn("PRIVATE-", context.tutoring["progress"]["pending_question"]["expected_answer"])


if __name__ == "__main__":
    unittest.main()
