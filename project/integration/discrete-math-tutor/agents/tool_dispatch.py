"""Synchronous Q3 tool dispatch with pairing, dedupe, timeout and pause.

Adapted from DeepTutor ``runtime/agentic/tool_dispatch.py``. The project's
LLM/store calls are synchronous, so ordinary tools run concurrently in a
small thread pool while pause tools run last, once the rest of the round has
settled. Every requested call receives exactly one role=tool message.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from contextvars import copy_context
from llm.execution_budget import current_budget, check_budget
from dataclasses import dataclass, field
import json
from typing import Any

from agents.tool_protocol import (
    BaseTool, CancelledError, ToolContext, ToolRegistry, ToolResult,
)

MAX_PARALLEL_TOOL_CALLS = 15
PAUSE_TOOLS = frozenset({"ask_user"})


@dataclass
class DispatchOutcome:
    tool_messages: list[dict[str, Any]] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    model_messages: list[dict[str, Any]] = field(default_factory=list, repr=False)
    results: list[ToolResult] = field(default_factory=list)
    pause: bool = False
    pause_payload: dict[str, Any] | None = None
    pause_tool_call_id: str | None = None
    terminate: bool = False
    terminate_payload: dict[str, Any] | None = None


def _normalise_call(call: Any, index: int) -> dict[str, Any]:
    if isinstance(call, dict):
        call_id = str(call.get("id") or call.get("tool_call_id") or f"call_{index}")
        name = str(call.get("name") or (call.get("function") or {}).get("name") or "")
        arguments = call.get("arguments")
        if arguments is None:
            arguments = (call.get("function") or {}).get("arguments")
    else:
        call_id = str(getattr(call, "id", "") or f"call_{index}")
        name = str(getattr(call, "name", "") or "")
        arguments = getattr(call, "arguments", None)
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments or "{}")
        except ValueError:
            arguments = {}
    if not isinstance(arguments, dict):
        arguments = {}
    if not name:
        raise ValueError(f"工具调用缺少名称：{call_id}")
    return {"id": call_id, "name": name, "arguments": arguments}


def _missing_required(tool: BaseTool, arguments: dict[str, Any]) -> list[str]:
    return [parameter.name for parameter in tool.definition.parameters
            if parameter.required and parameter.name not in arguments]


def _tool_message(call: dict[str, Any], result: ToolResult) -> dict[str, Any]:
    return {"role": "tool", "tool_call_id": call["id"], "name": call["name"],
            "content": result.content}


def _invoke(tool: BaseTool, call: dict[str, Any], context: ToolContext,
            timeout_seconds: float | None) -> ToolResult:
    check_budget()
    budget = current_budget.get()
    if budget:
        timeout_seconds = min(timeout_seconds or budget.remaining(), budget.remaining())
    context.check_cancelled()
    if tool is None:
        return ToolResult(content=f"{call['name']} 不在本轮工具列表中，未执行。", success=False)
    missing = _missing_required(tool, call["arguments"])
    if missing:
        return ToolResult(content=f"{call['name']} 缺少必要参数：{', '.join(missing)}", success=False)
    context.event("tool_call", call["name"], {"tool_call_id": call["id"],
        "arguments": {key: value for key, value in call["arguments"].items()
                      if key in {p.name for p in tool.definition.parameters
                                 if not p.sensitive}}})
    try:
        if timeout_seconds is None:
            result = tool.run(dict(call["arguments"]), context)
        else:
            pool = ThreadPoolExecutor(max_workers=1)
            future = pool.submit(copy_context().run, tool.run, dict(call["arguments"]), context)
            try:
                result = future.result(timeout=timeout_seconds)
            except FutureTimeout:
                # Do not wait for a hung retrieval/model-backed tool; the loop
                # must get a bounded failure result and finalize.
                pool.shutdown(wait=False, cancel_futures=True)
                raise
            else:
                pool.shutdown(wait=True)
        if not isinstance(result, ToolResult):
            result = ToolResult(content=str(result))
    except CancelledError:
        raise
    except FutureTimeout:
        result = ToolResult(content=f"{call['name']} 执行超时，未完成。", success=False)
    except Exception as exc:
        result = ToolResult(content=f"{call['name']} 执行失败：{type(exc).__name__}: {exc}", success=False)
    check_budget()
    context.event("tool_result", call["name"], {"tool_call_id": call["id"],
        "success": result.success, "sources": len(result.sources),
        "pause": bool(result.pause_for_user),
        "detail": (result.content or "")[:240]})
    return result


def dispatch_tool_calls(*, tool_calls: list[Any], registry: ToolRegistry,
                        context: ToolContext, max_calls: int = MAX_PARALLEL_TOOL_CALLS,
                        timeout_seconds: float | None = 30) -> DispatchOutcome:
    """Execute one assistant message's tool calls and preserve protocol pairing."""
    if not tool_calls:
        return DispatchOutcome()
    calls = [_normalise_call(call, index) for index, call in enumerate(tool_calls)]
    skipped = calls[max_calls:]
    calls = calls[:max_calls]
    outcome = DispatchOutcome()
    # Pairing for over-budget calls is still required for the next model call.
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    primary: list[tuple[int, dict[str, Any]]] = []
    for index, call in enumerate(calls):
        tool = registry.get(call["name"])
        key = (call["name"], ToolRegistry.canonical_arguments(call["arguments"]))
        if call["name"] in PAUSE_TOOLS and any(name in PAUSE_TOOLS for name, _ in seen):
            duplicate_of = next(value["id"] for (name, _), value in seen.items() if name in PAUSE_TOOLS)
        else:
            duplicate_of = seen.get(key, {}).get("id")
        if duplicate_of is not None:
            outcome.results.append(ToolResult(
                content=f"重复调用已跳过；相同调用 {duplicate_of} 已在执行。",
                metadata={"duplicate_of": duplicate_of}, success=False))
            outcome.tool_messages.append(_tool_message(call, outcome.results[-1]))
            continue
        seen[key] = call
        primary.append((index, call))

    ordinary = [(index, call) for index, call in primary if call["name"] not in PAUSE_TOOLS]
    pauses = [(index, call) for index, call in primary if call["name"] in PAUSE_TOOLS]
    resolved: dict[int, ToolResult] = {}
    if ordinary:
        with ThreadPoolExecutor(max_workers=min(8, len(ordinary))) as pool:
            futures = {index: pool.submit(copy_context().run, _invoke, registry.get(call["name"]), call, context,
                                          timeout_seconds) for index, call in ordinary}
            for index, future in futures.items():
                resolved[index] = future.result()
    for index, call in pauses:
        resolved[index] = _invoke(registry.get(call["name"]), call, context, timeout_seconds)

    for index, call in primary:
        result = resolved[index]
        outcome.results.append(result)
        outcome.tool_messages.append(_tool_message(call, result))
        outcome.sources.extend(result.sources)
        if result.model_message:
            for source in result.sources:
                if source.get('image_refs'):
                    source.setdefault('location', {})['model_message_anchor'] = call['id']
            outcome.model_messages.append({**result.model_message, '_after_tool_call_id': call['id']})
        if result.pause_for_user and not outcome.pause:
            outcome.pause = True
            outcome.pause_payload = {"tool_name": call["name"], "ask_user": result.pause_for_user}
            outcome.pause_tool_call_id = call["id"]
        if result.terminate_turn and not outcome.terminate:
            outcome.terminate = True
            outcome.terminate_payload = {"tool_name": call["name"], "content": result.content,
                                         "metadata": result.metadata}

    # Keep original order even though ordinary tools completed concurrently.
    ordered_messages = []
    for index, call in enumerate(calls):
        for message in outcome.tool_messages:
            if message["tool_call_id"] == call["id"]:
                ordered_messages.append(message)
                break
    for call in skipped:
        result = ToolResult(content=f"{call['name']} 未执行：单轮工具调用超过 {max_calls} 次上限。", success=False)
        outcome.results.append(result)
        ordered_messages.append(_tool_message(call, result))
    outcome.tool_messages = ordered_messages
    return outcome
