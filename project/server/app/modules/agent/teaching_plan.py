"""Short-term teaching-plan value objects."""

from dataclasses import dataclass, field
from typing import Literal


PlanStepType = Literal["diagnose", "teach", "check", "practice", "summarize"]
PlanStatus = Literal["active", "completed", "blocked"]


@dataclass(frozen=True)
class PlanStep:
    id: str
    step_type: PlanStepType
    completion_condition: str
    max_attempts: int = 2
    skippable: bool = False

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be positive")


@dataclass(frozen=True)
class ShortTermTeachingPlan:
    id: str
    knowledge_point_id: str | None
    steps: tuple[PlanStep, ...]
    current_step_index: int = 0
    status: PlanStatus = "active"
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 1 <= len(self.steps) <= 5:
            raise ValueError("short-term plans must contain between 1 and 5 steps")
        if not 0 <= self.current_step_index < len(self.steps):
            raise ValueError("current_step_index is outside the plan")

    @property
    def current_step(self) -> PlanStep:
        return self.steps[self.current_step_index]
