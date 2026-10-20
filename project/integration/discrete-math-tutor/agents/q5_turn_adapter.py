"""Minimal integration adapter for Q5 first batch.

The public application (main.py/TaskService/frontend) is not modified by Q5.
This adapter is the wiring surface for the integration window:
- generate a plan with the project LLM;
- confirm and start study;
- bind a Q2 textbook cursor or a Q2-resolved selection;
- return the current target/registry/tool_state for a Q3 LoopRequest.
"""
from __future__ import annotations

from typing import Any

from agents.q5_learning import LearningScope, Q5LearningService, intake_gaps
from agents.q5_plan_generator import LLMPlanGenerator
from agents.q5_tools import build_q5_registry


class Q5TurnAdapter:
    def __init__(self, service: Q5LearningService, scope: LearningScope) -> None:
        self.service = service
        self.scope = scope

    def status(self) -> dict[str, Any]:
        return self.service.status(self.scope)

    def intake_questions(self, profile: dict[str, Any] | None) -> list[dict[str, str]]:
        """Return only missing intake questions for Q3's ask_user payload."""
        return intake_gaps(profile)

    def generate_plan(
        self,
        *,
        goal: str,
        materials: list[dict[str, Any]],
        profile: dict[str, Any],
        llm: Any,
        command_id: str,
        path_name: str = "",
    ) -> dict[str, Any]:
        return self.service.generate_plan(
            self.scope,
            goal=goal,
            materials=materials,
            profile=profile,
            command_id=command_id,
            generator=LLMPlanGenerator(llm),
            path_name=path_name,
        )

    def confirm_and_start(
        self, path_id: str, path_revision: int, command_id: str
    ) -> dict[str, Any]:
        self.service.confirm_plan(
            self.scope,
            path_id,
            base_revision=path_revision,
            command_id=f"{command_id}:confirm",
        )
        self.service.set_mode(
            self.scope, "study", command_id=f"{command_id}:study"
        )
        return self.service.status(self.scope)

    def bind_textbook_cursor(
        self, cursor: dict[str, Any], command_id: str
    ) -> dict[str, Any]:
        return self.service.bind_textbook_target(
            self.scope, cursor, command_id=command_id
        )

    def bind_selection(
        self,
        selection: dict[str, Any],
        *,
        goal: str,
        command_id: str,
        path_id: str = "",
    ) -> dict[str, Any]:
        return self.service.bind_selection(
            self.scope,
            selection,
            goal=goal,
            command_id=command_id,
            path_id=path_id,
        )

    def loop_binding(self) -> dict[str, Any]:
        target = self.service.current_target(self.scope)
        if target is None:
            raise ValueError("no_current_learning_target")
        return {
            "target": target,
            "tools": build_q5_registry(self.service, self.scope),
            "tool_state": self.service.tool_state(self.scope),
        }


__all__ = ["Q5TurnAdapter"]
