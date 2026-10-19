"""Q3-compatible tool protocol used by the Q4 foundation.

The single source of truth is ``agents/tool_protocol.py`` on the Q3 branch
(``Q3_INTERFACE_CONTRACT.md`` section 2).  This module re-exports that protocol
when Q3 is present.  The fallback below exists only so the independent Q4
worktree can be tested before Q3 is committed; its shapes intentionally match
the contract one-for-one.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

try:  # Q3 is the owner of the runtime protocol.
    from agents.tool_protocol import (  # type: ignore[assignment]
        BaseTool,
        Cancellation,
        CancelledError,
        ToolContext,
        ToolDefinition,
        ToolParameter,
        ToolResult,
    )

    PROTOCOL_SOURCE = "q3"
except ImportError:  # pragma: no cover - exercised only before Q3 is merged
    PROTOCOL_SOURCE = "q4-contract-fallback"

    @dataclass(frozen=True)
    class ToolParameter:
        name: str
        type: str
        description: str = ""
        required: bool = True
        default: Any = None
        enum: list[str] | None = None
        items: dict[str, Any] | None = None
        sensitive: bool = False

        def to_schema(self) -> dict[str, Any]:
            schema: dict[str, Any] = {
                "type": self.type,
                "description": self.description,
            }
            if self.enum:
                schema["enum"] = self.enum
            if self.type == "array":
                schema["items"] = self.items if self.items is not None else {"type": "string"}
            return schema

    @dataclass(frozen=True)
    class ToolDefinition:
        name: str
        description: str
        parameters: tuple[ToolParameter, ...] = ()
        raw_parameters: dict[str, Any] | None = None

        def to_openai_schema(self) -> dict[str, Any]:
            if self.raw_parameters is not None:
                schema = dict(self.raw_parameters)
                schema.setdefault("type", "object")
                schema.setdefault("properties", {})
                return {
                    "type": "function",
                    "function": {
                        "name": self.name,
                        "description": self.description,
                        "parameters": schema,
                    },
                }
            properties: dict[str, Any] = {}
            required: list[str] = []
            for parameter in self.parameters:
                properties[parameter.name] = parameter.to_schema()
                if parameter.required:
                    required.append(parameter.name)
            return {
                "type": "function",
                "function": {
                    "name": self.name,
                    "description": self.description,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                },
            }

    @dataclass
    class ToolResult:
        content: str = ""
        sources: list[dict[str, Any]] = field(default_factory=list)
        metadata: dict[str, Any] = field(default_factory=dict)
        success: bool = True
        pause_for_user: dict[str, Any] | None = None
        terminate_turn: bool = False
        model_message: dict[str, Any] | None = field(default=None, repr=False)

        def __str__(self) -> str:
            return self.content

    class Cancellation:
        def __init__(self) -> None:
            self._cancelled = False

        def cancel(self) -> None:
            self._cancelled = True

        def is_cancelled(self) -> bool:
            return self._cancelled

        def check(self) -> None:
            if self._cancelled:
                raise CancelledError("task cancelled")

    class CancelledError(RuntimeError):
        pass

    @dataclass
    class ToolContext:
        student_id: str
        session_id: str
        task_id: str = ""
        request_id: str = ""
        knowledge_point: str = ""
        cancellation: Cancellation | None = None
        navigation: Any = None
        state: dict[str, Any] = field(default_factory=dict)
        emit: Callable[[str, str, dict[str, Any] | None], None] | None = None

        def check_cancelled(self) -> None:
            if self.cancellation is not None:
                self.cancellation.check()

        def event(
            self, event_type: str, message: str = "", metadata: dict | None = None
        ) -> None:
            if self.emit is not None:
                self.emit(event_type, message, metadata or {})

    class BaseTool(ABC):
        definition: ToolDefinition

        @abstractmethod
        def run(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
            raise NotImplementedError


def provider_identity(tool: Any) -> tuple[str, str]:
    """Return ``(kind, provider_id)`` for a provider tool, else ``("", "")``."""

    kind = str(getattr(tool, "provider_kind", "") or "")
    provider_id = str(
        getattr(tool, "provider_id", "") or getattr(tool, "server_name", "") or ""
    )
    return kind, provider_id


__all__ = [
    "BaseTool",
    "Cancellation",
    "CancelledError",
    "PROTOCOL_SOURCE",
    "ToolContext",
    "ToolDefinition",
    "ToolParameter",
    "ToolResult",
    "provider_identity",
]
