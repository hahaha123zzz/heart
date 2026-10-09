"""Pure Student State aggregation from verified learning signals.

Database adapters can map LearningEvidence/LearningEvent rows into
``StudentSignal`` without making this module depend on SQLAlchemy models.
"""

from dataclasses import dataclass
from typing import Iterable

from .contracts import StudentState


@dataclass(frozen=True)
class StudentSignal:
    """One evidence-backed observation about a learner."""

    knowledge_point_id: str | None = None
    mastery: float | None = None
    confidence: float | None = None
    misconception: str | None = None
    metacognition: float | None = None
    emotion: str | None = None
    source_ref: str | None = None
    weight: float = 1.0

    def __post_init__(self) -> None:
        if self.weight <= 0:
            raise ValueError("signal weight must be positive")
        for name in ("mastery", "confidence", "metacognition"):
            value = getattr(self, name)
            if value is not None and not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")


def _weighted_average(signals: list[StudentSignal], field: str) -> float | None:
    values = [
        (getattr(signal, field), signal.weight)
        for signal in signals
        if getattr(signal, field) is not None
    ]
    if not values:
        return None
    total_weight = sum(weight for _, weight in values)
    return sum(value * weight for value, weight in values) / total_weight


def build_student_state(
    signals: Iterable[StudentSignal],
    *,
    preferences: dict | None = None,
) -> StudentState:
    """Build a conservative snapshot; missing evidence stays unknown."""

    items = list(signals)
    misconceptions: list[str] = []
    evidence_refs: list[str] = []
    latest_emotion = None
    for signal in items:
        if signal.misconception and signal.misconception not in misconceptions:
            misconceptions.append(signal.misconception)
        if signal.source_ref and signal.source_ref not in evidence_refs:
            evidence_refs.append(signal.source_ref)
        if signal.emotion:
            latest_emotion = signal.emotion
    return StudentState(
        mastery=_weighted_average(items, "mastery"),
        confidence=_weighted_average(items, "confidence"),
        misconceptions=tuple(misconceptions),
        metacognition=_weighted_average(items, "metacognition"),
        emotion=latest_emotion,
        preferences=dict(preferences or {}),
        evidence_refs=tuple(evidence_refs),
    )
