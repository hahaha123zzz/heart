"""Argument parsing and validation before a tool is dispatched.

The required-argument guard is adapted from DeepTutor's
``runtime/agentic/tool_arg_guard.py``.  The type/enum checks are local additions
so a malformed model call cannot reach a tool that would misinterpret it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from agents.tools.protocol import ToolDefinition


@dataclass(frozen=True, slots=True)
class ArgumentIssue:
    code: str
    parameter: str
    message: str


@dataclass(frozen=True, slots=True)
class ValidationResult:
    ok: bool
    arguments: dict[str, Any]
    issues: tuple[ArgumentIssue, ...] = ()
    message: str = ""


def parse_arguments(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    """Parse model-authored arguments and require a JSON object."""

    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    if not isinstance(raw, str):
        raise ValueError("Tool arguments must be a JSON object or string")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Tool arguments are not valid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ValueError("Tool arguments must decode to a JSON object")
    return value


def _schema_rows(definition: ToolDefinition) -> list[tuple[str, str, bool, tuple[str, ...]]]:
    if definition.raw_parameters is not None:
        raw = definition.raw_parameters
        properties = raw.get("properties")
        properties = properties if isinstance(properties, dict) else {}
        required = raw.get("required")
        required_names = set(required) if isinstance(required, list) else set()
        rows: list[tuple[str, str, bool, tuple[str, ...]]] = []
        for name, prop in properties.items():
            if not isinstance(name, str) or not isinstance(prop, dict):
                continue
            enum = prop.get("enum")
            rows.append(
                (
                    name,
                    str(prop.get("type") or ""),
                    name in required_names and "default" not in prop,
                    tuple(str(value) for value in enum) if isinstance(enum, list) else (),
                )
            )
        return rows
    return [
        (
            parameter.name,
            parameter.type,
            parameter.required and parameter.default is None,
            tuple(str(value) for value in parameter.enum or ()),
        )
        for parameter in definition.parameters
    ]


def _is_supplied(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def normalize_arguments(
    definition: ToolDefinition,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Coerce only unambiguous scalar strings into the declared JSON type."""

    normalized = dict(arguments)
    for name, type_name, _required, _enum in _schema_rows(definition):
        if name not in normalized:
            continue
        value = normalized[name]
        if type_name == "integer" and isinstance(value, str) and value.strip().lstrip("-").isdigit():
            normalized[name] = int(value.strip())
        elif type_name == "number" and isinstance(value, str):
            try:
                normalized[name] = float(value)
            except ValueError:
                pass
        elif type_name == "boolean" and isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "false"}:
                normalized[name] = lowered == "true"
    return normalized


def validate_arguments(
    definition: ToolDefinition,
    arguments: dict[str, Any],
    *,
    allow_unknown: bool = True,
) -> ValidationResult:
    normalized = normalize_arguments(definition, arguments)
    rows = _schema_rows(definition)
    declared = {name for name, _type, _required, _enum in rows}
    issues: list[ArgumentIssue] = []

    for name, type_name, required, enum in rows:
        if name not in normalized or not _is_supplied(normalized[name]):
            if required:
                shape = type_name or "value"
                if enum:
                    shape += " (one of: " + " | ".join(enum) + ")"
                issues.append(
                    ArgumentIssue(
                        code="missing_required",
                        parameter=name,
                        message=f"`{name}` is required ({shape})",
                    )
                )
            continue
        value = normalized[name]
        if type_name and not _matches_type(value, type_name):
            issues.append(
                ArgumentIssue(
                    code="type_mismatch",
                    parameter=name,
                    message=f"`{name}` must be {type_name}, got {type(value).__name__}",
                )
            )
            continue
        if enum and str(value) not in enum:
            issues.append(
                ArgumentIssue(
                    code="invalid_enum",
                    parameter=name,
                    message=f"`{name}` must be one of: " + " | ".join(enum),
                )
            )

    if not allow_unknown:
        for name in normalized:
            if name in declared or name.startswith("_") or name == "event_sink":
                continue
            issues.append(
                ArgumentIssue(
                    code="unknown_argument",
                    parameter=name,
                    message=f"`{name}` is not declared by this tool",
                )
            )

    if not issues:
        return ValidationResult(ok=True, arguments=normalized)
    return ValidationResult(
        ok=False,
        arguments=normalized,
        issues=tuple(issues),
        message=validation_message(definition.name, issues),
    )


def validation_message(tool_name: str, issues: tuple[ArgumentIssue, ...]) -> str:
    details = "; ".join(issue.message for issue in issues)
    return (
        f"(tool call not dispatched — `{tool_name}` has invalid arguments: {details}. "
        "Re-emit the call with the declared argument names and value types.)"
    )


def _matches_type(value: Any, type_name: str) -> bool:
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "array":
        return isinstance(value, list)
    if type_name == "object":
        return isinstance(value, dict)
    return True


__all__ = [
    "ArgumentIssue",
    "ValidationResult",
    "normalize_arguments",
    "parse_arguments",
    "validate_arguments",
    "validation_message",
]
