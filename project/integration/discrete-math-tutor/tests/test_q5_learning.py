"""Q5 first batch: plan, confirm, explain, advance, resume, switch, source guard."""
from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from agents.agent_loop import LocalAgentLoop, LoopRequest
from agents.q3_navigation import StubLearningNavigator
from agents.q5_learning import (
    LearningScope,
    ObjectiveDraft,
    PlanDraft,
    Q5LearningService,
    Q5Navigator,
)
from agents.q5_plan_generator import LLMPlanGenerator
from agents.q5_tools import build_q5_registry
from agents.q5_turn_adapter import Q5TurnAdapter
from database import database as db
from database.models import Base, Student
from llm.client import ChatToolCall, ChatToolResult


def source_ref(unit_id: str, version: str = "v1") -> dict:
    return {
        "document_id": "doc-1",
        "version": version,
        "unit_id": unit_id,
        "chapter_id": 1,
        "section_id": 1,
        "page": 3,
        "title": f"unit {unit_id}",
    }


def draft() -> PlanDraft:
    return PlanDraft(
        goal="掌握实验设计基础",
        name="实验设计入门",
        modules=[
            (
                "基础概念",
                "能区分并解释自变量和因变量",
                [
                    ObjectiveDraft("自变量", "concept", [source_ref("ch1:s1:b1")]),
                    ObjectiveDraft("因变量", "concept", [source_ref("ch1:s1:b2")]),
                ],
            ),
            (
                "研究设计",
                "能比较被试内与被试间设计",
                [
                    ObjectiveDraft(
                        "被试内设计", "concept", [source_ref("ch1:s2:b1")]
                    ),
                ],
            ),
        ],
    )


class StaticGenerator:
    def __init__(self, value: PlanDraft):
        self.value = value
        self.kwargs = {}

    def generate(self, **kwargs):
        self.kwargs = kwargs
        return self.value


class FakePlanLLM:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def chat_json(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        return self.payload


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


def tool_round(name, arguments):
    return ChatToolResult(
        text="",
        finish_reason="tool_calls",
        tool_calls=[
            ChatToolCall(
                id="call_1",
                name=name,
                arguments=arguments,
                raw_arguments=json.dumps(arguments, ensure_ascii=False),
            )
        ],
    )


def final_round(text):
    return ChatToolResult(text=text, finish_reason="stop", tool_calls=[])


class Q5TestBase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            "sqlite:///" + self.temp.name.replace("\\", "/") + "/q5.db",
            connect_args={"check_same_thread": False, "timeout": 10},
        )

        @event.listens_for(self.engine, "connect")
        def fk(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        import database.q5_learning as q5_models  # noqa: F401

        Base.metadata.create_all(self.engine)
        self.db_patch = patch.object(
            db,
            "SessionLocal",
            sessionmaker(
                bind=self.engine, autoflush=False, expire_on_commit=False
            ),
        )
        self.db_patch.start()
        with db.session_scope() as session:
            session.add(Student(student_id="s", account_type="test"))
        self.scope = LearningScope(
            student_id="s", session_id="sess", course_id="course-1"
        )
        self.service = Q5LearningService(
            source_validator=lambda ref: str(ref.get("version") or "") == "v1"
        )

    def tearDown(self):
        self.db_patch.stop()
        self.engine.dispose()
        self.temp.cleanup()

    def make_plan(self, command_id="plan-1", value=None):
        generator = StaticGenerator(value or draft())
        return self.service.generate_plan(
            self.scope,
            goal="掌握实验设计基础",
            materials=[source_ref("ch1:s1:b1")],
            profile={"prior_knowledge": "无"},
            command_id=command_id,
            generator=generator,
        )

    def confirmed_plan(self):
        made = self.make_plan()
        self.service.confirm_plan(
            self.scope,
            made["path_id"],
            base_revision=made["path_revision"],
            command_id="confirm-1",
        )
        self.service.set_mode(self.scope, "study", command_id="mode-1")
        return made


class PlanLifecycleTests(Q5TestBase):
    def test_generate_confirm_start_explaining(self):
        made = self.make_plan()
        self.assertEqual(made["status"], "draft")
        self.assertFalse(made["plan_confirmed"])
        status = self.service.status(self.scope)
        self.assertEqual(status["status"], "draft")
        self.assertEqual(status["mode"], "outline")
        self.assertEqual(status["current"]["name"], "自变量")
        self.assertEqual(len(status["modules"]), 2)
        self.assertEqual(
            status["modules"][0]["objectives"][0]["source_refs"][0]["version"],
            "v1",
        )

        confirmed = self.service.confirm_plan(
            self.scope,
            made["path_id"],
            base_revision=made["path_revision"],
            command_id="confirm-1",
        )
        self.assertTrue(confirmed["plan_confirmed"])
        self.assertEqual(confirmed["status"], "active")
        self.assertEqual(confirmed["mode"], "outline")
        started = self.service.set_mode(self.scope, "study", command_id="mode-1")
        self.assertEqual(started["mode"], "study")
        self.assertEqual(self.service.status(self.scope)["current"]["name"], "自变量")

    def test_study_requires_explicit_confirmation(self):
        self.make_plan()
        with self.assertRaises(ValueError):
            self.service.set_mode(self.scope, "study", command_id="mode-without-confirm")

    def test_plan_generation_receives_materials_and_profile(self):
        generator = StaticGenerator(draft())
        self.service.generate_plan(
            self.scope,
            goal="掌握实验设计基础",
            materials=[source_ref("ch1:s1:b1")],
            profile={"prior_knowledge": "学过一点"},
            command_id="plan-gen",
            generator=generator,
        )
        self.assertEqual(generator.kwargs["goal"], "掌握实验设计基础")
        self.assertEqual(generator.kwargs["materials"][0]["version"], "v1")
        self.assertEqual(generator.kwargs["profile"]["prior_knowledge"], "学过一点")

    def test_llm_generator_returns_validated_draft(self):
        payload = {
            "name": "实验设计入门",
            "modules": [
                {
                    "name": "基础概念",
                    "objective": "能区分自变量和因变量",
                    "objectives": [
                        {
                            "name": "自变量",
                            "type": "concept",
                            "source_refs": [source_ref("ch1:s1:b1")],
                        }
                    ],
                }
            ],
        }
        llm = FakePlanLLM(payload)
        generator = LLMPlanGenerator(llm)
        value = generator.generate(
            goal="掌握实验设计基础",
            materials=[source_ref("ch1:s1:b1")],
            profile={"prior_knowledge": "无"},
        )
        self.assertIsInstance(value, PlanDraft)
        self.assertEqual(value.modules[0][2][0].name, "自变量")
        self.assertEqual(llm.calls[0]["messages"][0]["role"], "system")

    def test_ordinary_turn_does_not_create_a_plan(self):
        status = self.service.status(self.scope)
        self.assertEqual(status["status"], "no_path")
        self.assertIsNone(status.get("path_id"))
        paths = self.service.list_paths(self.scope)
        self.assertEqual(paths, [])

    def test_duplicate_generate_command_is_replayed(self):
        first = self.make_plan(command_id="same")
        second = self.make_plan(command_id="same")
        self.assertTrue(second["replayed"])
        self.assertEqual(first["path_id"], second["path_id"])
        self.assertEqual(len(self.service.list_paths(self.scope)), 1)


class ExplainAndAdvanceTests(Q5TestBase):
    def test_explain_then_understood_advances_without_mastery(self):
        made = self.confirmed_plan()
        status = self.service.status(self.scope)
        objective_id = status["current"]["objective_id"]
        explained = self.service.record_explained(
            self.scope,
            objective_id,
            summary="解释了自变量是研究者操纵的变量",
            command_id="explain-1",
        )
        self.assertEqual(explained["current"]["objective_id"], objective_id)
        self.assertTrue(
            self.service.status(self.scope)["current"]["explained"]
        )

        advanced = self.service.mark_understood(
            self.scope, command_id="understood-1"
        )
        self.assertEqual(advanced["status"], "advanced")
        self.assertEqual(advanced["previous"]["objective_id"], objective_id)
        self.assertEqual(advanced["current"]["name"], "因变量")
        self.assertNotIn("mastered", advanced)
        self.assertFalse(
            self.service.status(self.scope)["modules"][0]["objectives"][0][
                "mastered"
            ]
        )

    def test_duplicate_understood_does_not_advance_twice(self):
        self.confirmed_plan()
        first = self.service.mark_understood(self.scope, command_id="u-1")
        second = self.service.mark_understood(self.scope, command_id="u-1")
        self.assertTrue(second["replayed"])
        self.assertEqual(
            self.service.status(self.scope)["current"]["objective_id"],
            first["current"]["objective_id"],
        )
        third = self.service.mark_understood(self.scope, command_id="u-2")
        self.assertEqual(third["status"], "advanced")
        self.assertNotEqual(
            self.service.status(self.scope)["current"]["objective_id"],
            first["current"]["objective_id"],
        )

    def test_concurrent_understood_advances_only_once(self):
        self.confirmed_plan()
        status = self.service.status(self.scope)
        barrier = threading.Barrier(2)
        results: list[object] = []

        def worker(command_id: str) -> None:
            barrier.wait()
            try:
                results.append(
                    self.service.mark_understood(
                        self.scope,
                        command_id=command_id,
                        base_revision=status["path_revision"],
                    )
                )
            except Exception as exc:
                results.append(exc)

        threads = [
            threading.Thread(target=worker, args=("concurrent-a",)),
            threading.Thread(target=worker, args=("concurrent-b",)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        advanced = [row for row in results if isinstance(row, dict)]
        conflicts = [
            row for row in results if isinstance(row, ValueError)
        ]
        self.assertEqual(len(advanced), 1, results)
        self.assertEqual(len(conflicts), 1, results)
        self.assertEqual(str(conflicts[0]), "path_conflict")
        after = self.service.status(self.scope)
        self.assertEqual(after["current"]["name"], "因变量")

    def test_understood_revision_conflict_does_not_advance(self):
        self.confirmed_plan()
        status = self.service.status(self.scope)
        with self.assertRaises(ValueError):
            self.service.mark_understood(
                self.scope,
                command_id="stale",
                base_revision=status["path_revision"] - 1,
            )
        self.assertEqual(
            self.service.status(self.scope)["current"]["objective_id"],
            status["current"]["objective_id"],
        )
        advanced = self.service.mark_understood(
            self.scope,
            command_id="fresh",
            base_revision=status["path_revision"],
        )
        self.assertEqual(advanced["status"], "advanced")

    def test_refresh_reuses_binding_and_position(self):
        self.confirmed_plan()
        first = self.service.mark_understood(self.scope, command_id="u-1")
        fresh = Q5LearningService(
            source_validator=lambda ref: str(ref.get("version") or "") == "v1"
        )
        status = fresh.status(self.scope)
        self.assertEqual(status["path_id"], first["path_id"])
        self.assertEqual(status["current"]["objective_id"], first["current"]["objective_id"])
        self.assertTrue(status["modules"][0]["objectives"][0]["understood"])

    def test_understood_at_end_reports_teaching_complete_not_mastery(self):
        self.confirmed_plan()
        self.service.mark_understood(self.scope, command_id="u-1")
        self.service.mark_understood(self.scope, command_id="u-2")
        last = self.service.mark_understood(self.scope, command_id="u-3")
        self.assertTrue(last["teaching_complete"])
        status = self.service.status(self.scope)
        self.assertIsNone(status["current"])
        self.assertTrue(status["teaching_complete"])
        self.assertFalse(status["path_complete"])


class PathSwitchTests(Q5TestBase):
    def test_switch_and_leave_preserve_each_path_position(self):
        first = self.confirmed_plan()
        self.service.mark_understood(self.scope, command_id="a-1")
        second = self.make_plan(command_id="plan-b", value=PlanDraft(
            goal="掌握另一个主题",
            name="另一条路径",
            modules=[
                (
                    "另一模块",
                    "能解释另一个目标",
                    [ObjectiveDraft("另一目标", "concept", [source_ref("ch2:s1:b1")])],
                )
            ],
        ))
        self.service.confirm_plan(
            self.scope,
            second["path_id"],
            base_revision=second["path_revision"],
            command_id="b-confirm",
        )
        self.service.set_mode(self.scope, "study", command_id="b-mode")
        self.assertEqual(self.service.status(self.scope)["path_id"], second["path_id"])
        self.assertEqual(self.service.status(self.scope)["current"]["name"], "另一目标")

        self.service.switch_path(
            self.scope, first["path_id"], command_id="back-a"
        )
        restored = self.service.status(self.scope)
        self.assertEqual(restored["path_id"], first["path_id"])
        self.assertEqual(restored["current"]["name"], "因变量")

        self.service.leave_path(self.scope, command_id="leave")
        self.assertEqual(self.service.status(self.scope)["status"], "no_path")
        self.service.switch_path(
            self.scope, first["path_id"], command_id="resume-a"
        )
        self.assertEqual(self.service.status(self.scope)["current"]["name"], "因变量")

    def test_switch_rejects_other_students_path(self):
        made = self.confirmed_plan()
        other = LearningScope(student_id="s2", session_id="sess2")
        with db.session_scope() as session:
            session.add(Student(student_id="s2", account_type="test"))
        with self.assertRaises(PermissionError):
            self.service.switch_path(other, made["path_id"], command_id="steal")


class SourceAndReviseTests(Q5TestBase):
    def test_invalid_source_blocks_status_and_advance(self):
        made = self.confirmed_plan()
        service = Q5LearningService(
            source_validator=lambda ref: str(ref.get("version") or "") != "v1"
        )
        status = service.status(self.scope)
        self.assertEqual(status["status"], "source_unavailable")
        with self.assertRaises(ValueError):
            service.mark_understood(self.scope, command_id="blocked")

    def test_revise_protects_explained_objective(self):
        self.confirmed_plan()
        status = self.service.status(self.scope)
        objective_id = status["current"]["objective_id"]
        self.service.record_explained(
            self.scope, objective_id, summary="已讲解", command_id="explain"
        )
        with self.assertRaises(ValueError):
            self.service.revise_objective(
                self.scope,
                status["path_id"],
                objective_id,
                "新名字",
                base_revision=status["path_revision"],
                command_id="revise-1",
            )

    def test_revise_requires_outline_mode(self):
        made = self.confirmed_plan()
        status = self.service.status(self.scope)
        with self.assertRaises(ValueError):
            self.service.revise_objective(
                self.scope,
                made["path_id"],
                status["current"]["objective_id"],
                "新名字",
                base_revision=status["path_revision"],
                command_id="revise-2",
            )

    def test_revise_draft_objective_before_confirmation(self):
        made = self.make_plan()
        status = self.service.status(self.scope)
        objective_id = status["current"]["objective_id"]
        revised = self.service.revise_objective(
            self.scope,
            made["path_id"],
            objective_id,
            "自变量（修正）",
            base_revision=status["path_revision"],
            command_id="revise-ok",
        )
        self.assertEqual(revised["name"], "自变量（修正）")
        refreshed = self.service.status(self.scope)
        self.assertEqual(refreshed["current"]["name"], "自变量（修正）")
        self.assertEqual(refreshed["path_revision"], status["path_revision"] + 1)


class SelectionBindingTests(Q5TestBase):
    def selection(self):
        return {
            "document_id": "doc-1",
            "version": "v1",
            "unit_id": "ch1:s1:b1",
            "chapter_id": 1,
            "section_id": 1,
            "page": 3,
            "title": "自变量",
            "text": "自变量是研究者操纵的变量。",
        }

    def test_selection_creates_path_and_survives_without_reselection(self):
        made = self.service.bind_selection(
            self.scope,
            self.selection(),
            goal="学习圈选内容",
            command_id="selection-1",
        )
        self.assertEqual(made["status"], "draft")
        status = self.service.status(self.scope)
        self.assertEqual(status["current"]["name"], "自变量")
        self.assertEqual(
            status["current"]["source_refs"][0]["unit_id"], "ch1:s1:b1"
        )
        self.assertEqual(len(self.service.list_paths(self.scope)), 1)

        self.service.confirm_plan(
            self.scope,
            made["path_id"],
            base_revision=made["path_revision"],
            command_id="selection-confirm",
        )
        self.service.set_mode(self.scope, "study", command_id="selection-mode")
        objective_id = self.service.status(self.scope)["current"]["objective_id"]
        self.service.record_explained(
            self.scope,
            objective_id,
            summary="解释了自变量",
            command_id="selection-explain",
        )
        fresh = Q5LearningService(
            source_validator=lambda ref: str(ref.get("version") or "") == "v1"
        )
        self.assertEqual(
            fresh.status(self.scope)["current"]["objective_id"], objective_id
        )

    def test_selection_binds_existing_path_by_source(self):
        made = self.make_plan()
        result = self.service.bind_selection(
            self.scope,
            self.selection(),
            goal="学习圈选内容",
            command_id="selection-bind",
            path_id=made["path_id"],
        )
        self.assertEqual(result["status"], "selection_bound")
        self.assertEqual(
            self.service.status(self.scope)["current"]["name"], "自变量"
        )
        self.assertEqual(len(self.service.list_paths(self.scope)), 1)

    def test_selection_requires_document_and_version(self):
        broken = dict(self.selection())
        broken.pop("version")
        with self.assertRaises(ValueError):
            self.service.bind_selection(
                self.scope,
                broken,
                goal="学习圈选内容",
                command_id="selection-broken",
            )


class TextbookNavigationTests(Q5TestBase):
    def target(self, unit_id="ch1:s1:b6", title="实验心理学的含义"):
        return {
            "id": unit_id,
            "title": title,
            "chapter_id": 1,
            "section_id": 1,
            "version": "v1",
            "page": 3,
            "source": "doc-1",
        }

    def test_q2_target_is_projected_without_local_next_cursor(self):
        first = self.service.bind_textbook_target(
            self.scope, self.target(), command_id="nav-1"
        )
        self.assertEqual(first["status"], "navigation_bound")
        status = self.service.status(self.scope)
        self.assertEqual(status["path"]["kind"], "textbook_navigation")
        self.assertEqual(status["current"]["name"], "实验心理学的含义")
        self.assertEqual(self.service.current_target(self.scope).target_id, "ch1:s1:b6")

        second = self.service.bind_textbook_target(
            self.scope,
            self.target("ch1:s1:b20", "主要讲心理学实验方法的教材"),
            command_id="nav-2",
        )
        self.assertEqual(second["status"], "navigation_bound")
        status = self.service.status(self.scope)
        self.assertEqual(status["current"]["name"], "主要讲心理学实验方法的教材")
        self.assertEqual(self.service.current_target(self.scope).target_id, "ch1:s1:b20")

    def test_understood_on_textbook_path_asks_q2_for_next(self):
        self.service.bind_textbook_target(
            self.scope, self.target(), command_id="nav-1"
        )
        result = self.service.mark_understood(self.scope, command_id="nav-understood")
        self.assertEqual(result["status"], "understood")
        self.assertTrue(result["requires_navigation"])
        self.assertEqual(
            self.service.status(self.scope)["current"]["name"], "实验心理学的含义"
        )


class Q5TurnAdapterTests(Q5TestBase):
    def test_intake_only_asks_missing_fields(self):
        adapter = Q5TurnAdapter(self.service, self.scope)
        questions = adapter.intake_questions({"prior_knowledge": "学过一点"})
        ids = [item["id"] for item in questions]
        self.assertNotIn("prior_knowledge", ids)
        self.assertEqual(len(ids), 3)
        full = adapter.intake_questions(
            {
                "prior_knowledge": "a",
                "target_level": "b",
                "time_budget": "c",
                "preferences": "d",
            }
        )
        self.assertEqual(full, [])

    def test_adapter_generates_confirms_and_binds_loop(self):
        payload = {
            "name": "适配器路径",
            "modules": [
                {
                    "name": "基础",
                    "objective": "能解释基本变量",
                    "objectives": [
                        {
                            "name": "自变量",
                            "type": "concept",
                            "source_refs": [source_ref("ch1:s1:b1")],
                        }
                    ],
                }
            ],
        }
        adapter = Q5TurnAdapter(self.service, self.scope)
        made = adapter.generate_plan(
            goal="掌握基础",
            materials=[source_ref("ch1:s1:b1")],
            profile={"prior_knowledge": "无"},
            llm=FakePlanLLM(payload),
            command_id="adapter-plan",
        )
        self.assertEqual(made["status"], "draft")
        started = adapter.confirm_and_start(
            made["path_id"], made["path_revision"], "adapter-start"
        )
        self.assertEqual(started["mode"], "study")
        binding = adapter.loop_binding()
        self.assertEqual(binding["target"].name, "自变量")
        self.assertIn("mastery_status", binding["tools"].names())
        self.assertEqual(
            binding["tool_state"]["q5_path_id"], made["path_id"]
        )


class Q3LoopIntegrationTests(Q5TestBase):
    def test_q5_navigator_exposes_current_target_without_reparsing(self):
        self.confirmed_plan()
        navigator = Q5Navigator(self.service, self.scope)
        decision = navigator.resolve(
            message="下一部分",
            student_id="s",
            session_id="sess",
            current_target=None,
            context=None,
        )
        self.assertEqual(decision.action, "teach")
        self.assertIsNotNone(decision.target)
        self.assertEqual(decision.target.name, "自变量")

    def test_q3_loop_calls_q4_authorized_q5_note_tool(self):
        self.confirmed_plan()
        status = self.service.status(self.scope)
        objective_id = status["current"]["objective_id"]
        registry = build_q5_registry(self.service, self.scope)
        self.assertIn("mastery_status", registry.names())
        self.assertIn("mastery_note_explained", registry.names())
        llm = ScriptedLLM(
            [
                tool_round(
                    "mastery_note_explained",
                    {
                        "knowledge_point_id": objective_id,
                        "summary": "解释了自变量",
                    },
                ),
                final_round("自变量是研究者操纵的变量。[1]"),
            ]
        )
        target = self.service.current_target(self.scope)
        result = LocalAgentLoop(llm).run(
            LoopRequest(
                student_id="s",
                session_id="sess",
                task_id="task-1",
                request_id="req-1",
                message="请解释自变量",
                system_prompt="你是助教。",
                tools=registry,
                target=target,
                navigation=StubLearningNavigator(target=target),
                tool_state=self.service.tool_state(self.scope),
                max_exploration_rounds=3,
                max_settlement_rounds=1,
            )
        )
        self.assertTrue(result.completed)
        self.assertEqual(result.final_text, "自变量是研究者操纵的变量。[1]")
        refreshed = self.service.status(self.scope)
        self.assertTrue(refreshed["current"]["explained"])
        self.assertFalse(refreshed["current"]["mastered"])

    def test_q3_loop_understood_tool_advances_without_mastery(self):
        self.confirmed_plan()
        registry = build_q5_registry(self.service, self.scope)
        llm = ScriptedLLM(
            [
                tool_round("mastery_understood", {}),
                final_round("好的，下一部分。"),
            ]
        )
        target = self.service.current_target(self.scope)
        result = LocalAgentLoop(llm).run(
            LoopRequest(
                student_id="s",
                session_id="sess",
                task_id="task-understood",
                request_id="req-understood",
                message="我懂了，下一部分",
                system_prompt="你是助教。",
                tools=registry,
                target=target,
                navigation=StubLearningNavigator(target=target),
                tool_state=self.service.tool_state(self.scope),
                max_exploration_rounds=3,
                max_settlement_rounds=1,
            )
        )
        self.assertTrue(result.completed)
        status = self.service.status(self.scope)
        self.assertEqual(status["current"]["name"], "因变量")
        self.assertFalse(status["current"]["mastered"])
        self.assertIn("mastery_understood", registry.names())

    def test_side_question_does_not_move_teaching_position(self):
        self.confirmed_plan()
        before = self.service.status(self.scope)
        registry = build_q5_registry(self.service, self.scope)
        llm = ScriptedLLM([final_round("这是对插问的回答，不改变学习位置。")])
        target = self.service.current_target(self.scope)
        result = LocalAgentLoop(llm).run(
            LoopRequest(
                student_id="s",
                session_id="sess",
                task_id="task-side",
                request_id="req-side",
                message="顺便问一个无关问题",
                system_prompt="你是助教。",
                tools=registry,
                target=target,
                navigation=StubLearningNavigator(target=target),
                tool_state=self.service.tool_state(self.scope),
                max_exploration_rounds=2,
                max_settlement_rounds=1,
            )
        )
        self.assertTrue(result.completed)
        after = self.service.status(self.scope)
        self.assertEqual(after["current"]["objective_id"], before["current"]["objective_id"])
        self.assertEqual(after["path_revision"], before["path_revision"])

    def test_q4_build_tool_persists_a_draft(self):
        registry = build_q5_registry(self.service, self.scope)
        from agents.tool_protocol import ToolContext

        context = ToolContext(
            student_id="s", session_id="sess", task_id="build-task",
            request_id="req-build",
        )
        tool = registry.get("mastery_build")
        self.assertIsNotNone(tool)
        result = tool.run(
            {
                "goal": "掌握实验设计基础",
                "path_name": "工具生成路径",
                "modules": [
                    {
                        "name": "基础概念",
                        "objective": "能解释实验设计的基本变量",
                        "objectives": [
                            {
                                "name": "自变量",
                                "type": "concept",
                                "source_refs": [source_ref("ch1:s1:b1")],
                            }
                        ],
                    }
                ],
            },
            context,
        )
        self.assertTrue(result.success, result.content)
        status = self.service.status(self.scope)
        self.assertEqual(status["status"], "draft")
        self.assertEqual(status["path"]["name"], "工具生成路径")
        mode_tool = registry.get("mastery_mode")
        mode = mode_tool.run(
            {"mode": "study", "confirm": True, "reason": "学生已认可计划"},
            context,
        )
        self.assertTrue(mode.success, mode.content)
        started = self.service.status(self.scope)
        self.assertEqual(started["mode"], "study")
        self.assertTrue(started["plan_confirmed"])
        self.assertEqual(started["status"], "active")


if __name__ == "__main__":
    unittest.main()
