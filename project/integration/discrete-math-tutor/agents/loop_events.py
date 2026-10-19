"""Serializable Q3 loop events and an adapter to the project's progress callback."""
from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any, Callable


@dataclass(frozen=True)
class LoopEvent:
    type: str
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "message": self.message,
                "metadata": self.metadata, "timestamp": self.timestamp}


class EventCollector:
    """Collect events for persistence while forwarding a safe progress view."""

    def __init__(self, progress: Callable[[str, str, str], None] | None = None) -> None:
        self.events: list[LoopEvent] = []
        self.progress = progress

    def __call__(self, event_type: str, message: str = "",
                 metadata: dict[str, Any] | None = None) -> None:
        self.events.append(LoopEvent(event_type, message, metadata or {}))
        if self.progress is not None:
            detail = message or str((metadata or {}).get("detail") or "")
            self.progress("loop-" + event_type, event_type, detail[:300])

    def to_dicts(self) -> list[dict[str, Any]]:
        return [event.to_dict() for event in self.events]

    def by_type(self, event_type: str) -> list[LoopEvent]:
        return [event for event in self.events if event.type == event_type]
