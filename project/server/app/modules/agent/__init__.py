"""Shared teaching-agent domain contracts.

This package is intentionally independent from HTTP routers and SQLAlchemy models.
It is the seam through which Tutor, Chat, Practice and Review can gradually move
to one decision loop without changing their public APIs in one step.
"""

from .contracts import AgentContext, IntentDecision, InteractionIntent, StudentState
from .intent_router import route_interaction
from .student_state import StudentSignal, build_student_state

__all__ = [
    "AgentContext",
    "IntentDecision",
    "InteractionIntent",
    "StudentState",
    "StudentSignal",
    "build_student_state",
    "route_interaction",
]
