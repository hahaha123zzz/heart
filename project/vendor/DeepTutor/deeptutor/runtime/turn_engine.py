"""Shared lower-level execution engine used by every application adapter."""

from __future__ import annotations

from collections.abc import AsyncIterator

from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream import StreamEvent, StreamEventType


_external_input_preparer = None
_external_context_preparer = None


def set_external_input_preparer(preparer) -> None:
    global _external_input_preparer
    _external_input_preparer = preparer


def set_external_context_preparer(preparer) -> None:
    global _external_context_preparer
    _external_context_preparer = preparer


class TurnEngine:
    """Execute an assembled context through the canonical orchestrator."""

    def __init__(self, capability_registry=None) -> None:  # noqa: ANN001
        self.capability_registry = capability_registry

    async def execute(self, context: UnifiedContext) -> AsyncIterator[StreamEvent]:
        # Lazy loading avoids provider/plugin import side effects at process
        # boot and leaves one stable patch point for tests and embedders.
        if _external_context_preparer is not None:
            await _external_context_preparer(context)
        if _external_input_preparer is not None:
            async for event in _external_input_preparer(context):
                yield event
                if event.type == StreamEventType.DONE:
                    return
        from deeptutor.runtime.orchestrator import ChatOrchestrator

        orchestrator = (
            ChatOrchestrator()
            if self.capability_registry is None
            else ChatOrchestrator(capability_registry=self.capability_registry)
        )
        async for event in orchestrator.handle(context):
            yield event


_default_engine: TurnEngine | None = None


def get_turn_engine() -> TurnEngine:
    global _default_engine
    if _default_engine is None:
        _default_engine = TurnEngine()
    return _default_engine


__all__ = ["TurnEngine", "get_turn_engine"]
