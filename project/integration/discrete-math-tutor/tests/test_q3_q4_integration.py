"""Integration checks for Q3 loop + Q4 authorized tool registry + Q3 gate."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agents.agent_loop import LoopResult
from agents.agent_loop_service import (
    _default_navigator, _map_result, _target_from_context, run_agent_loop_turn,
)
from agents.q3_navigation import LearningTarget, SourceRef, StubLearningNavigator
from agents.q3_tools import RetrieveCourseTool, build_registry
from agents.quality_checker import QualityChecker
from agents.teaching_planner import TeachingPlan
from agents.tool_protocol import ToolContext
from llm.client import ChatToolCall, ChatToolResult
from models.chat_request import ChatRequest
from models.student_state import StudentState
from models.task_context import TaskContext


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "visualization" / "skills"


class ScriptedLLM:
    def __init__(self, rounds):
        self.rounds = list(rounds)
        self.calls = []

    def chat_with_tools(self, messages, tools, **kwargs):
        self.calls.append({"messages": messages, "tools": tools, **kwargs})
        item = self.rounds.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeMemory:
    def read_version(self, student_id, point):
        return "token", 0

    def append_exchange(self, *args, **kwargs):
        return 1


def tool_round(name, arguments):
    return ChatToolResult(
        text="", finish_reason="tool_calls",
        tool_calls=[ChatToolCall(id="call_1", name=name, arguments=arguments,
                                 raw_arguments=json.dumps(arguments, ensure_ascii=False))],
    )


class RecordingQualityLLM:
    def __init__(self, payload=None):
        self.payload = payload or {"passed": True, "issues": [], "suggestions": ""}
        self.calls = []

    def chat_json(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        return self.payload


class RegistryIntegrationTests(unittest.TestCase):
    def test_q4_registry_is_the_q3_turn_registry(self):
        registry = build_registry(skills_root=SKILLS, allow_skills=True)
        self.assertEqual(type(registry).__name__, "ScopedToolRegistry")
        self.assertIn("retrieve_course", registry.names())
        self.assertIn("ask_user", registry.names())
        self.assertIn("read_skill", registry.names())
        self.assertIsNone(registry.get("workspace_read"))

    def test_workspace_tools_are_mounted_only_with_explicit_grant(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "note.txt").write_text("hello q3", encoding="utf-8")
            registry = build_registry(workspace_root=root, allow_workspace=True,
                                      allow_skills=False)
            self.assertIn("workspace_read", registry.names())
            context = ToolContext(student_id="s", session_id="x",
                                  state={"workspace_root": str(root)})
            result = registry.get("workspace_read").run({"path": "note.txt"}, context)
            self.assertTrue(result.success)
            self.assertIn("hello q3", result.content)

    def test_read_skill_uses_bound_project_skill_root(self):
        registry = build_registry(skills_root=SKILLS, allow_skills=True)
        context = ToolContext(student_id="s", session_id="x",
                              state={"skills_root": str(SKILLS)})
        result = registry.get("read_skill").run({"name": "finite-structures"}, context)
        self.assertTrue(result.success)
        self.assertIn("finite-structures", result.content)

    def test_progress_callback_receives_string_details(self):
        llm = ScriptedLLM([ChatToolResult(text="回答[1]", finish_reason="stop")])
        orchestrator = SimpleNamespace(llm=llm, memory=FakeMemory(), quality_checker=None)
        context = TaskContext(student_id="s", message="请解释这个概念。",
                              knowledge_point="自变量")
        request = ChatRequest(student_id="s", session_id="legacy", request_id="progress-1",
                              message=context.message)
        events = []
        result = run_agent_loop_turn(
            orchestrator=orchestrator, request=request, context=context,
            navigator=StubLearningNavigator(target=LearningTarget(
                target_id="kp:自变量", name="自变量")),
            publish_gate=lambda text, state: (True, ""), llm=llm,
            progress=lambda stage, label, detail: events.append((stage, label, detail)),
        )
        self.assertEqual(result["answer_status"], "answered")
        self.assertTrue(events)
        self.assertTrue(any(stage.startswith("loop-") for stage, _, _ in events))
        self.assertTrue(all(isinstance(detail, str) for _, _, detail in events))

    def test_loop_executes_q4_skill_tool_and_keeps_state(self):
        llm = ScriptedLLM([
            tool_round("read_skill", {"name": "finite-structures"}),
            ChatToolResult(text="技能已读取。[1]", finish_reason="stop"),
        ])
        orchestrator = SimpleNamespace(llm=llm, memory=FakeMemory(), quality_checker=None)
        context = TaskContext(student_id="s", message="请解释这个概念。",
                              knowledge_point="自变量")
        request = ChatRequest(student_id="s", session_id="legacy", request_id="tool-1",
                              message=context.message)
        result = run_agent_loop_turn(
            orchestrator=orchestrator, request=request, context=context,
            navigator=StubLearningNavigator(target=LearningTarget(
                target_id="kp:自变量", name="自变量")),
            publish_gate=lambda text, state: (True, ""), llm=llm,
        )
        self.assertEqual(result["answer_status"], "answered")
        self.assertEqual(result["loop_summary"]["tool_steps"], 1)
        tool_messages = [message for message in llm.calls[1]["messages"]
                         if message.get("role") == "tool"]
        self.assertTrue(tool_messages)
        self.assertEqual(tool_messages[0]["name"], "read_skill")
        self.assertIn("finite-structures", tool_messages[0]["content"])


class GlobalSourceNumberingTests(unittest.TestCase):
    def _target(self):
        return LearningTarget(target_id="ch1:s1:b1", name="自变量",
                              chapter_id=1, section_id=1)

    def _source(self, text, page=1):
        return SourceRef(source_id=text, document_id="doc", text=text, page=page)

    def test_retrieval_numbers_sources_across_calls(self):
        target = self._target()
        navigation = StubLearningNavigator(
            target=target, sources=[self._source("甲"), self._source("乙")])
        context = ToolContext(student_id="s", session_id="x", navigation=navigation,
                              state={"learning_target": target, "source_offset": 5,
                                     "max_sources": 24})
        result = RetrieveCourseTool().run({"query": "自变量", "limit": 2}, context)
        self.assertTrue(result.success)
        self.assertEqual([item["index"] for item in result.sources], [6, 7])
        self.assertIn("[6]", result.content)
        self.assertIn("[7]", result.content)

    def test_parallel_retrieval_calls_keep_unique_global_numbers(self):
        from agents.tool_dispatch import dispatch_tool_calls
        from agents.tool_protocol import ToolRegistry

        target = self._target()

        class QueryNavigator:
            def resolve(self, **kwargs):
                raise AssertionError("not used")

            def search(self, *, target, query, limit, preferred_types=()):
                return [self._source(f"{query}-1"), self._source(f"{query}-2")]

            @staticmethod
            def _source(text):
                return SourceRef(source_id=text, document_id="doc", text=text, page=1)

        context = ToolContext(student_id="s", session_id="x", navigation=QueryNavigator(),
                              state={"learning_target": target, "source_offset": 0,
                                     "max_sources": 24})
        registry = ToolRegistry(); registry.register(RetrieveCourseTool())
        outcome = dispatch_tool_calls(tool_calls=[
            {"id": "a", "name": "retrieve_course", "arguments": {"query": "甲", "limit": 2}},
            {"id": "b", "name": "retrieve_course", "arguments": {"query": "乙", "limit": 2}},
        ], registry=registry, context=context)
        indexes = sorted(source["index"] for source in outcome.sources)
        self.assertEqual(indexes, [1, 2, 3, 4])
        for message in outcome.tool_messages:
            self.assertIn("retrieve_course", message["name"])

    def test_repeated_retrieval_of_same_source_returns_no_duplicate(self):
        target = self._target()
        navigation = StubLearningNavigator(target=target, sources=[self._source("甲")])
        context = ToolContext(student_id="s", session_id="x", navigation=navigation,
                              state={"learning_target": target, "source_offset": 0,
                                     "max_sources": 24})
        first = RetrieveCourseTool().run({"query": "自变量", "limit": 2}, context)
        second = RetrieveCourseTool().run({"query": "自变量", "limit": 2}, context)
        self.assertTrue(first.success)
        self.assertEqual(len(first.sources), 1)
        self.assertFalse(second.success)
        self.assertTrue(second.metadata.get("duplicate_retrieval"))
        self.assertFalse(second.sources)

    def test_map_result_only_publishes_cited_sources(self):
        target = self._target()
        result = LoopResult(
            final_text="回答[2]", completed=True,
            sources=[
                {"index": 1, "source_id": "a", "document_id": "doc", "text": "甲"},
                {"index": 2, "source_id": "b", "document_id": "doc", "text": "乙"},
                {"index": 3, "source_id": "c", "document_id": "doc", "text": "丙"},
            ],
        )
        mapped = _map_result(result, target)
        self.assertEqual(len(mapped["textbook_sources"]), 3)
        self.assertEqual([ref["source_index"] for ref in mapped["pdf_references"]], [1])
        self.assertEqual(mapped["pdf_references"][0]["evidence"]["evidence_id"], "b")

    def test_retrieval_budget_stops_extra_searches(self):
        target = self._target()
        navigation = StubLearningNavigator(target=target, sources=[self._source("甲")])
        context = ToolContext(student_id="s", session_id="x", navigation=navigation,
                              state={"learning_target": target, "source_offset": 24,
                                     "max_sources": 24})
        result = RetrieveCourseTool().run({"query": "自变量", "limit": 2}, context)
        self.assertFalse(result.success)
        self.assertTrue(result.metadata.get("source_budget_exhausted"))
        self.assertIn("预算已用完", result.content)


class HostNavigationTests(unittest.TestCase):
    def _row(self):
        return {
            "status": "ready", "id": "ch1:s1:b20", "title": "心理学实验方法的类型",
            "chapter_id": 1, "section_id": 1, "version": "v1",
        }

    def test_host_course_navigation_is_the_authoritative_target(self):
        context = TaskContext(student_id="s", message="继续下一个知识点",
                              knowledge_point="心理学实验方法的类型",
                              course_navigation=self._row())
        target = _target_from_context(context)
        self.assertEqual(target.target_id, "ch1:s1:b20")
        self.assertEqual(target.chapter_id, 1)
        self.assertEqual(target.section_id, 1)
        self.assertEqual(target.version, "v1")

    def test_next_topic_is_not_turned_back_into_clarification(self):
        llm = ScriptedLLM([ChatToolResult(text="下一个知识点是实验方法的类型。[1]",
                                          finish_reason="stop")])
        orchestrator = SimpleNamespace(llm=llm, memory=FakeMemory(), quality_checker=None)
        context = TaskContext(student_id="s", message="继续下一个知识点",
                              knowledge_point="心理学实验方法的类型",
                              course_navigation=self._row())
        request = ChatRequest(student_id="s", session_id="legacy", request_id="next-1",
                              message=context.message)
        result = run_agent_loop_turn(
            orchestrator=orchestrator, request=request, context=context,
            publish_gate=lambda text, state: (True, ""), llm=llm,
        )
        self.assertEqual(result["answer_status"], "answered")
        self.assertEqual(result["loop_summary"]["target"], "ch1:s1:b20")

    def test_host_search_keeps_sources_inside_the_selected_section(self):
        target = LearningTarget(target_id="ch1:s1:b20", name="心理学实验方法的类型",
                                chapter_id=1, section_id=1, version="v1")
        navigation = _default_navigator(target, self._row())

        def chunk(chapter, section, text):
            return SimpleNamespace(
                chapter_id=chapter, section_id=section, text=text, source="doc",
                document_id="doc", version="", page=1, quote=text,
                image_refs=[], id=f"ch{chapter}:s{section}", chunk_id="",
            )

        rows = [chunk(1, 1, "目标小节内容"), chunk(2, 1, "其他章节内容")]
        with patch("knowledge.course_navigation.read_target", return_value=[]), \
                patch("knowledge.local_rag.course_retrieval.retrieve", return_value=rows):
            sources = navigation.search(target=target, query="实验方法", limit=6)
        self.assertEqual(len(sources), 1)
        self.assertIn("目标小节内容", sources[0].text)
        self.assertEqual(sources[0].chapter_id, 1)

    def test_host_search_prefers_the_exact_navigation_block(self):
        target = LearningTarget(target_id="ch1:s1:b20", name="心理学实验方法的类型",
                                chapter_id=1, section_id=1, version="v1")
        navigation = _default_navigator(target, self._row())
        exact = SimpleNamespace(
            chapter_id=1, section_id=1, text="目标块原文", source="doc",
            document_id="doc", version="v1", page=1, quote="目标块原文",
            image_refs=[], id="ch1:s1:b20", chunk_id="",
        )
        with patch("knowledge.course_navigation.read_target", return_value=[exact]), \
                patch("knowledge.local_rag.course_retrieval.retrieve",
                      side_effect=AssertionError("generic retrieval must not run")):
            sources = navigation.search(target=target, query="实验方法", limit=6)
        self.assertEqual(len(sources), 1)
        self.assertIn("目标块原文", sources[0].text)


class CitationFormatGateTests(unittest.TestCase):
    def test_valid_markers_pass_and_malformed_number_text_is_rejected(self):
        from agents.agent_loop_service import _citation_format_issues

        self.assertEqual(_citation_format_issues("结论[1][2,3][4-5]。"), "")
        self.assertIn("引用格式无效",
                      _citation_format_issues("结论[1 第二组检索结果第1条，即摘录一)。]"))


class AgentLoopQualityGateTests(unittest.TestCase):
    def test_loop_mode_scopes_quality_issues_to_publishability(self):
        llm = RecordingQualityLLM()
        checker = QualityChecker(llm)
        plan = TeachingPlan(goal="解释自变量", strategy="scaffolding",
                            action="explain", difficulty="medium")
        result = checker.check(
            "自变量是研究者操纵的变量。[1]", StudentState(), plan,
            "请解释自变量。", context={"agent_loop": True,
                                        "reply_maximum_override": 800},
            textbook_excerpts="[1] 自变量是研究者操纵的变量。",
        )
        self.assertTrue(result.passed)
        messages = llm.calls[0]["messages"]
        system = messages[0]["content"]
        user = messages[1]["content"]
        self.assertIn("只检查可发布性", system)
        self.assertIn("只把下列问题列为 issues", user)
        self.assertNotIn("遗漏任一比较对象", user)
        self.assertIn("800", user)

    def test_loop_mode_still_rejects_unsupported_citation(self):
        llm = RecordingQualityLLM()
        checker = QualityChecker(llm)
        plan = TeachingPlan(goal="解释自变量", strategy="scaffolding",
                            action="explain", difficulty="medium")
        with patch("knowledge.citation_guard.citation_issues",
                   return_value=["引用[2]不在本轮教材证据中"]) as guard:
            result = checker.check(
                "自变量是研究者操纵的变量。[2]", StudentState(), plan,
                "请解释自变量。", context={"agent_loop": True,
                                            "reply_maximum_override": 800},
                textbook_excerpts="[1] 文档 第2页\n自变量是研究者操纵的变量。",
            )
        self.assertFalse(result.passed)
        self.assertTrue(result.issues)
        guard.assert_called_once()
        self.assertFalse(llm.calls, "rule-level citation failure must not call the model")


if __name__ == "__main__":
    unittest.main()
