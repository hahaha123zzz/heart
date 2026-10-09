"""Pure domain contracts for the shared teaching-agent loop.

The contracts use immutable snapshots so a planner cannot accidentally mutate a
SQLAlchemy session while making a decision.
"""

from dataclasses import dataclass, field
from typing import Any, Literal


InteractionIntent = Literal[
    "continue_teaching", "ask_question", "ask_hint", "change_topic", "review",
    "practice", "summarize", "pause",
]


@dataclass(frozen=True)
class StudentState:
    mastery: float | None = None
    confidence: float | None = None
    misconceptions: tuple[str, ...] = ()
    metacognition: float | None = None
    emotion: str | None = None
    preferences: dict[str, Any] = field(default_factory=dict)
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("mastery", "confidence", "metacognition"):
            value = getattr(self, name)
            if value is not None and not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")


@dataclass(frozen=True)
class AgentContext:
    student_text: str
    current_teaching_state: str | None = None
    current_topic: str | None = None
    student_state: StudentState = field(default_factory=StudentState)
    active_plan_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IntentDecision:
    intent: InteractionIntent
    confidence: float
    reason: str
    matched_rule: str | None = None
    interrupt_current_flow: bool = False

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
