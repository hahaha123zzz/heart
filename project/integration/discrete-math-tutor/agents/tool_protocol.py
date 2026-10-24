"""Project-local tool protocol for the Q3 agent loop.

Adapted from DeepTutor ``deeptutor/core/tool_protocol.py`` at the pinned
source revision. Tools are synchronous here because the project's task,
memory and retrieval paths are synchronous; the loop still enforces the same
schema, dedupe, pairing and pause semantics.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import json
import threading
from typing import Any, Callable


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
        schema: dict[str, Any] = {"type": self.type, "description": self.description}
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
            return {"type": "function", "function": {
                "name": self.name, "description": self.description, "parameters": schema}}
        properties = {}
        required = []
        for parameter in self.parameters:
            properties[parameter.name] = parameter.to_schema()
            if parameter.required:
                required.append(parameter.name)
        return {"type": "function", "function": {
            "name": self.name,
            "description": self.description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        }}


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
    """Cooperative cancellation shared by the task API and the loop."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def check(self) -> None:
        if self.is_cancelled():
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

    source_lock: Any = field(default_factory=threading.RLock, repr=False)
    deadline: float | None = None

    def check_cancelled(self) -> None:
        from time import monotonic
        from llm.execution_budget import check_budget
        check_budget()
        if self.deadline is not None and monotonic() >= self.deadline:
            raise TimeoutError("工具本轮截止时间已到，拒绝迟到状态提交")
        if self.cancellation is not None:
            self.cancellation.check()

    def event(self, event_type: str, message: str = "", metadata: dict | None = None) -> None:
        if self.emit is not None:
            self.emit(event_type, message, metadata or {})


class BaseTool(ABC):
    definition: ToolDefinition

    @abstractmethod
    def run(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        raise NotImplementedError


class ToolRegistry:
    """A per-turn registry; it never grants tools the caller did not mount."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        name = tool.definition.name
        if not name or name in self._tools:
            raise ValueError(f"工具名重复或为空：{name!r}")
        self._tools[name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def definitions(self, names: list[str] | None = None) -> list[ToolDefinition]:
        selected = names if names is not None else list(self._tools)
        return [self._tools[name].definition for name in selected if name in self._tools]

    def schemas(self, names: list[str] | None = None) -> list[dict[str, Any]]:
        return [definition.to_openai_schema() for definition in self.definitions(names)]

    @staticmethod
    def canonical_arguments(arguments: dict[str, Any]) -> str:
        return json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
