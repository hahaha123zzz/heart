"""Tool catalogues and per-turn authorized views for the Q3 registry.

The public surface (``register``/``get``/``names``/``definitions``/``schemas``/
``canonical_arguments``) matches ``agents/tool_protocol.py`` on the Q3 branch.
Q4 adds lazy built-in specs, aliases, plugin discovery, and an authorization
proxy that refuses unmounted/ungranted tools at execution time.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import inspect
import logging
import threading
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents.tools.protocol import (
    BaseTool,
    ToolContext,
    ToolDefinition,
    ToolResult,
    provider_identity,
)
from agents.tools.scope import Allowlist, ToolGrant
from agents.tools.validation import validate_arguments

logger = logging.getLogger(__name__)

DEFAULT_PLUGIN_GROUP = "heart.tools"


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Import-cheap catalogue entry for a built-in or plugin tool."""

    name: str
    loader: Callable[[], BaseTool]
    deferred: bool = False

    @classmethod
    def from_class_path(
        cls,
        name: str,
        class_path: str,
        *,
        deferred: bool = False,
    ) -> "ToolSpec":
        module_path, class_name = class_path.rsplit(":", 1)

        def _load() -> BaseTool:
            module = importlib.import_module(module_path)
            tool_type = getattr(module, class_name)
            if not isinstance(tool_type, type) or not issubclass(tool_type, BaseTool):
                raise TypeError(f"{class_path!r} did not resolve to a BaseTool class")
            return tool_type()

        return cls(name=name, loader=_load, deferred=deferred)

    def create(self) -> BaseTool:
        tool = self.loader()
        if not isinstance(tool, BaseTool):
            raise TypeError(f"Tool spec {self.name!r} did not create a BaseTool")
        if tool.definition.name != self.name:
            raise RuntimeError(
                f"Tool catalogue drift: {self.name!r} created {tool.definition.name!r}"
            )
        if self.deferred:
            tool.deferred = True
        return tool


class ToolRegistry:
    """Process registry with lazy built-ins, aliases, and plugin discovery."""

    def __init__(
        self,
        *,
        aliases: Mapping[str, tuple[str, Mapping[str, Any]]] | None = None,
    ) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._tools: dict[str, BaseTool] = {}
        self._load_errors: dict[str, str] = {}
        self._lock = threading.RLock()
        self._aliases: dict[str, tuple[str, dict[str, Any]]] = {
            str(name): (str(target), dict(defaults))
            for name, (target, defaults) in (aliases or {}).items()
        }

    # -- registration -------------------------------------------------
    def register(self, tool: BaseTool, *, replace: bool = False) -> None:
        if not isinstance(tool, BaseTool):
            raise TypeError("register() expects a BaseTool instance")
        name = tool.definition.name
        self._validate_name(name)
        with self._lock:
            if not replace and (name in self._tools or name in self._specs):
                raise ValueError(f"Tool {name!r} is already registered")
            self._specs.pop(name, None)
            self._tools[name] = tool
            self._load_errors.pop(name, None)

    def register_spec(self, spec: ToolSpec, *, replace: bool = False) -> None:
        self._validate_name(spec.name)
        with self._lock:
            if not replace and (spec.name in self._tools or spec.name in self._specs):
                raise ValueError(f"Tool {spec.name!r} is already registered")
            self._tools.pop(spec.name, None)
            self._specs[spec.name] = spec

    def unregister(self, name: str) -> None:
        with self._lock:
            self._tools.pop(name, None)
            self._specs.pop(name, None)
            self._load_errors.pop(name, None)

    def load_builtins(self, specs: Iterable[ToolSpec] | None = None) -> None:
        if specs is None:
            from agents.tools.local_specs import LOCAL_TOOL_SPECS

            specs = LOCAL_TOOL_SPECS
        for spec in specs:
            with self._lock:
                if spec.name in self._tools or spec.name in self._specs:
                    continue
                self._specs[spec.name] = spec

    def load_plugins(
        self,
        *,
        group: str = DEFAULT_PLUGIN_GROUP,
        entries: Iterable[Any] | None = None,
    ) -> list[str]:
        """Load provider tools from entry points without shadowing built-ins."""

        loaded: list[str] = []
        for entry in entries if entries is not None else _entry_points(group):
            try:
                candidate = entry.load()
            except Exception:
                logger.warning("Failed to load tool entry point %r", entry, exc_info=True)
                continue
            try:
                tool = _coerce_tool(candidate)
            except Exception:
                logger.warning("Failed to construct tool entry point %r", entry, exc_info=True)
                continue
            if tool is None:
                logger.warning("Tool entry point %r did not produce a BaseTool", entry)
                continue
            try:
                name = tool.definition.name
            except Exception:
                logger.warning("Tool entry point %r has no valid definition", entry, exc_info=True)
                continue
            if name in self._tools or name in self._specs:
                logger.warning("Tool entry point %r shadows %r; ignored", entry, name)
                continue
            try:
                self.register(tool)
            except (TypeError, ValueError):
                logger.warning("Invalid tool entry point %r", entry, exc_info=True)
                continue
            loaded.append(name)
        return loaded

    # -- resolution ---------------------------------------------------
    def resolve_request(
        self,
        name: str,
        kwargs: Mapping[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        name = str(name or "").strip()
        supplied = dict(kwargs or {})
        with self._lock:
            if name in self._tools or name in self._specs:
                return name, supplied
            target, defaults = self._aliases.get(name, (name, {}))
        return target, {**defaults, **supplied}

    def get(self, name: str) -> BaseTool | None:
        resolved, _ = self.resolve_request(name)
        with self._lock:
            tool = self._tools.get(resolved)
            if tool is not None:
                return tool
            spec = self._specs.get(resolved)
        if spec is None:
            return None
        try:
            tool = spec.create()
        except Exception as exc:
            logger.warning("Failed to load tool %r", resolved, exc_info=True)
            with self._lock:
                self._load_errors[resolved] = f"{type(exc).__name__}: {exc}"
            return None
        with self._lock:
            existing = self._tools.get(resolved)
            if existing is not None:
                return existing
            self._tools[resolved] = tool
            return tool

    def names(self) -> list[str]:
        with self._lock:
            names = list(self._specs)
            names.extend(name for name in self._tools if name not in self._specs)
        return names

    def list_tools(self) -> list[str]:
        return self.names()

    def definitions(self, names: Iterable[str] | None = None) -> list[ToolDefinition]:
        selected = list(names) if names is not None else self.names()
        out: list[ToolDefinition] = []
        seen: set[str] = set()
        for requested in selected:
            tool = self.get(requested)
            if tool is None or tool.definition.name in seen:
                continue
            seen.add(tool.definition.name)
            out.append(tool.definition)
        return out

    def schemas(self, names: Iterable[str] | None = None) -> list[dict[str, Any]]:
        return [definition.to_openai_schema() for definition in self.definitions(names)]

    def get_enabled(self, names: Iterable[str]) -> list[BaseTool]:
        enabled: list[BaseTool] = []
        seen: set[str] = set()
        for requested in names:
            tool = self.get(requested)
            if tool is None or tool.definition.name in seen:
                continue
            enabled.append(tool)
            seen.add(tool.definition.name)
        return enabled

    def get_definitions(self, names: Iterable[str] | None = None) -> list[ToolDefinition]:
        return self.definitions(names)

    def build_openai_schemas(self, names: Iterable[str] | None = None) -> list[dict[str, Any]]:
        return self.schemas(names)

    def deferred_tools(self) -> list[BaseTool]:
        with self._lock:
            deferred_names = [name for name, spec in self._specs.items() if spec.deferred]
            deferred_names.extend(
                name
                for name, tool in self._tools.items()
                if getattr(tool, "deferred", False) and name not in deferred_names
            )
        return [tool for tool in (self.get(name) for name in deferred_names) if tool is not None]

    def run(
        self,
        name: str,
        arguments: dict[str, Any] | None,
        context: ToolContext,
    ) -> ToolResult:
        resolved, defaults = self.resolve_request(name, arguments)
        tool = self.get(resolved)
        if tool is None:
            error = self._load_errors.get(resolved)
            suffix = f" ({error})" if error else ""
            raise KeyError(f"Unknown tool: {name}{suffix}")
        merged = {**defaults, **dict(arguments or {})}
        result = tool.run(merged, context)
        return _coerce_result(result)

    @staticmethod
    def canonical_arguments(arguments: dict[str, Any]) -> str:
        import json

        return json.dumps(
            arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )

    @property
    def load_errors(self) -> dict[str, str]:
        with self._lock:
            return dict(self._load_errors)

    @staticmethod
    def _validate_name(name: str) -> None:
        if not isinstance(name, str) or not name:
            raise ValueError("Tool name must be a non-empty string")
        if not all(char.isalnum() or char in "_-." for char in name):
            raise ValueError(f"Invalid tool name: {name!r}")


class AuthorizationProxy(BaseTool):
    """Q3 BaseTool wrapper that enforces the Q4 per-turn grant at execution."""

    def __init__(
        self,
        inner: BaseTool,
        grant: ToolGrant,
        refusal_message: str = "",
        default_arguments: Mapping[str, Any] | None = None,
    ) -> None:
        self._inner = inner
        self._grant = grant
        self._default_arguments = dict(default_arguments or {})
        self.definition = inner.definition
        self.scopes = tuple(getattr(inner, "scopes", ()) or ())
        self.read_only = bool(getattr(inner, "read_only", True))
        self.deferred = bool(getattr(inner, "deferred", False))
        self._refusal_message = refusal_message or (
            "This tool is not available in this conversation. Only tools granted "
            "for this task can be called."
        )
        for attribute in ("provider_kind", "provider_id", "server_name"):
            if hasattr(inner, attribute):
                setattr(self, attribute, getattr(inner, attribute))

    def run(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        context.check_cancelled()
        if not self._grant.allows_tool(self.definition.name):
            return self._refuse("unauthorized_tool")
        if not self._grant.allows_scopes(self.scopes):
            return self._refuse("missing_scope")
        mismatch = self._root_mismatch(context)
        if mismatch:
            return ToolResult(
                content=self._refusal_message,
                success=False,
                metadata={"error": "root_mismatch", "root": mismatch, "tool": self.definition.name},
            )
        merged = {**self._default_arguments, **dict(arguments or {})}
        validation = validate_arguments(
            self.definition,
            merged,
            allow_unknown=self.definition.raw_parameters is not None,
        )
        if not validation.ok:
            return ToolResult(
                content=validation.message,
                success=False,
                metadata={
                    "error": "invalid_arguments",
                    "tool": self.definition.name,
                    "issues": [
                        {
                            "code": issue.code,
                            "parameter": issue.parameter,
                            "message": issue.message,
                        }
                        for issue in validation.issues
                    ],
                },
            )
        return self._inner.run(validation.arguments, context)

    def _root_mismatch(self, context: ToolContext) -> str:
        scopes = set(self.scopes)
        if any(scope.startswith("workspace:") for scope in scopes):
            expected = self._grant.workspace_root
            actual = context.state.get("workspace_root")
            if expected is not None and (
                not actual or Path(str(actual)).resolve() != expected.resolve()
            ):
                return "workspace_root"
        if any(scope.startswith("skills:") for scope in scopes):
            expected = self._grant.skills_root
            actual = context.state.get("skills_root")
            if expected is not None and (
                not actual or Path(str(actual)).resolve() != expected.resolve()
            ):
                return "skills_root"
        return ""

    def _refuse(self, code: str) -> ToolResult:
        logger.info("Scoped registry refused tool %r: %s", self.definition.name, code)
        return ToolResult(
            content=self._refusal_message,
            success=False,
            metadata={"error": code, "tool": self.definition.name},
        )


class ScopedToolRegistry:
    """Per-turn Q3-compatible registry containing only granted tools.

    The view is built once from the process catalogue and an optional overlay.
    Q3's ``dispatch_tool_calls`` can therefore treat it exactly like its own
    ``ToolRegistry``; a name that was never mounted cannot be resolved.
    """

    def __init__(
        self,
        *,
        base: ToolRegistry,
        overlay: Iterable[BaseTool] = (),
        grant: ToolGrant | None = None,
        selected: Iterable[str] | None = None,
        refusal_message: str = "",
    ) -> None:
        self._base = base
        self._grant = grant or ToolGrant()
        self._selected = {str(name) for name in selected} if selected is not None else None
        self._tools: dict[str, BaseTool] = {}
        self._overlay_candidates: dict[str, BaseTool] = {}
        self._lock = threading.RLock()
        for tool in overlay:
            name = tool.definition.name
            if base.get(name) is not None:
                logger.error(
                    "Overlay tool %r collides with a shared tool; dropped",
                    name,
                )
                continue
            self._overlay_candidates[name] = tool
            if self._selected is not None and name not in self._selected:
                continue
            if self._authorized(tool):
                self._tools[name] = AuthorizationProxy(
                    tool, self._grant, refusal_message
                )
        self._overlay_names = set(self._tools)

    @property
    def grant(self) -> ToolGrant:
        return self._grant

    def _authorized(self, tool: BaseTool) -> bool:
        return self._grant.allows_tool(tool.definition.name) and self._grant.allows_scopes(
            tuple(getattr(tool, "scopes", ()) or ())
        )

    def _ensure_base_loaded(self) -> None:
        with self._lock:
            for name in self._base.names():
                if name in self._tools:
                    continue
                if self._selected is not None and name not in self._selected:
                    continue
                if not self._grant.allows_tool(name):
                    continue
                tool = self._base.get(name)
                if tool is None or not self._authorized(tool):
                    continue
                self._tools[name] = AuthorizationProxy(tool, self._grant)

    def get(self, name: str) -> BaseTool | None:
        self._ensure_base_loaded()
        resolved, defaults = self.resolve_request(name)
        with self._lock:
            tool = self._tools.get(resolved)
            if tool is None or not defaults:
                return tool
            inner = getattr(tool, "_inner", None)
            if inner is None:
                return tool
            return AuthorizationProxy(
                inner,
                self._grant,
                getattr(tool, "_refusal_message", ""),
                default_arguments=defaults,
            )

    def mount_tool(self, tool: BaseTool) -> bool:
        """Mount a deferred tool after ``load_tools`` loaded its schema.

        Non-deferred tools must already be in ``selected``. A deferred tool may
        be mounted later because that is the point of progressive disclosure,
        but it still must pass the per-turn tool-name and resource grant.
        """
        name = tool.definition.name
        with self._lock:
            existing = self._tools.get(name)
            if existing is not None:
                return getattr(existing, "_inner", None) is tool
            overlay = self._overlay_candidates.get(name)
            if overlay is not None and overlay is not tool:
                logger.error("Deferred mount %r does not match the turn overlay", name)
                return False
            base_tool = self._base.get(name)
            if base_tool is not None and base_tool is not tool:
                logger.error("Deferred mount %r would replace a shared tool", name)
                return False
            if (
                self._selected is not None
                and name not in self._selected
                and not getattr(tool, "deferred", False)
            ):
                return False
            if not self._authorized(tool):
                return False
            self._tools[name] = AuthorizationProxy(tool, self._grant)
            self._overlay_names.add(name)
            return True

    def names(self) -> list[str]:
        self._ensure_base_loaded()
        with self._lock:
            out = [name for name in self._base.names() if name in self._tools]
            out.extend(
                name
                for name in sorted(self._overlay_names)
                if name in self._tools and name not in out
            )
            return out

    def list_tools(self) -> list[str]:
        return self.names()

    def definitions(self, names: Iterable[str] | None = None) -> list[ToolDefinition]:
        selected = list(names) if names is not None else self.names()
        out: list[ToolDefinition] = []
        seen: set[str] = set()
        for requested in selected:
            tool = self.get(requested)
            if tool is None or tool.definition.name in seen:
                continue
            seen.add(tool.definition.name)
            out.append(tool.definition)
        return out

    def schemas(self, names: Iterable[str] | None = None) -> list[dict[str, Any]]:
        return [definition.to_openai_schema() for definition in self.definitions(names)]

    def get_enabled(self, names: Iterable[str]) -> list[BaseTool]:
        self._ensure_base_loaded()
        return [tool for tool in (self.get(name) for name in names) if tool is not None]

    def get_definitions(self, names: Iterable[str] | None = None) -> list[ToolDefinition]:
        return self.definitions(names)

    def build_openai_schemas(self, names: Iterable[str] | None = None) -> list[dict[str, Any]]:
        return self.schemas(names)

    def deferred_tools(self) -> list[BaseTool]:
        return [
            tool
            for tool in (self.get(name) for name in self.names())
            if tool is not None and getattr(tool, "deferred", False)
        ]

    def resolve_request(
        self,
        name: str,
        kwargs: Mapping[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        if name in self._overlay_names:
            return name, dict(kwargs or {})
        resolver = getattr(self._base, "resolve_request", None)
        if callable(resolver):
            return resolver(name, kwargs)
        return str(name), dict(kwargs or {})

    def run(
        self,
        name: str,
        arguments: dict[str, Any] | None,
        context: ToolContext,
    ) -> ToolResult:
        tool = self.get(name)
        if tool is None:
            return ToolResult(
                content=f"工具 {name!r} 不在本轮已挂载列表中，未执行。",
                success=False,
                metadata={"error": "unauthorized_tool", "tool": name},
            )
        return tool.run(dict(arguments or {}), context)

    @staticmethod
    def canonical_arguments(arguments: dict[str, Any]) -> str:
        return ToolRegistry.canonical_arguments(arguments)


def _entry_points(group: str) -> list[Any]:
    discovered = importlib.metadata.entry_points()
    if hasattr(discovered, "select"):
        return list(discovered.select(group=group))
    return list(discovered.get(group, []))  # pragma: no cover - old Python


def _coerce_tool(candidate: Any) -> BaseTool | None:
    value = candidate
    if inspect.isclass(value):
        value = value()
    elif callable(value) and not isinstance(value, BaseTool):
        value = value()
    return value if isinstance(value, BaseTool) else None


def _coerce_result(result: Any) -> ToolResult:
    if isinstance(result, ToolResult):
        return result
    if isinstance(result, str):
        return ToolResult(content=result)
    return ToolResult(content=str(result))


__all__ = [
    "AuthorizationProxy",
    "DEFAULT_PLUGIN_GROUP",
    "ScopedToolRegistry",
    "ToolRegistry",
    "ToolSpec",
]
