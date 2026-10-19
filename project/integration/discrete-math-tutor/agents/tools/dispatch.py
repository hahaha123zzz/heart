"""Thin Q4 bridge to the Q3-owned tool dispatcher.

Q3 owns ``agents/tool_dispatch.py``: pairing, de-duplication, parallel
execution, timeout, pause ordering, and failure results.  Q4 deliberately does
not implement a second dispatcher.  This module exists so callers can resolve
the dependency once and get a clear error when Q3 is not present.
"""

from __future__ import annotations

from typing import Any

from agents.tools.protocol import ToolContext
from agents.tools.registry import ScopedToolRegistry, ToolRegistry


class Q3DispatchUnavailable(RuntimeError):
    pass


def dispatch_tool_calls(
    *,
    tool_calls: list[Any],
    registry: ScopedToolRegistry | ToolRegistry,
    context: ToolContext,
    max_calls: int = 15,
    timeout_seconds: float | None = 30,
):
    """Delegate one assistant message's tool batch to Q3's dispatcher."""

    try:
        from agents.tool_dispatch import dispatch_tool_calls as q3_dispatch
    except ImportError as exc:  # pragma: no cover - Q3 is present after merge
        raise Q3DispatchUnavailable(
            "Q3 tool_dispatch is not available; Q4 does not ship a parallel dispatcher."
        ) from exc
    return q3_dispatch(
        tool_calls=tool_calls,
        registry=registry,
        context=context,
        max_calls=max_calls,
        timeout_seconds=timeout_seconds,
    )


__all__ = ["Q3DispatchUnavailable", "dispatch_tool_calls"]
