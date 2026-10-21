"""Project-local agent loop for Q3.

This is the local adaptation of DeepTutor's ``AgentLoop``. It runs inside the
project's task identity, uses the project LLM client, and never starts the
upstream application. Tool execution, pause/resume, cancellation and the
publish gate are injected by the caller.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from copy import deepcopy
import json
from typing import Any, Callable

from agents.ask_user_contract import format_user_reply, substitute_answer
from agents.loop_events import EventCollector
from agents.q3_navigation import LearningTarget
from agents.tool_dispatch import DispatchOutcome, dispatch_tool_calls
from agents.tool_protocol import (
    Cancellation, CancelledError, ToolContext, ToolRegistry, ToolResult,
)
from llm.client import LLMClient, LLMError
from llm.answer_events import answer_kwargs, checking, retract
from agents.transient_messages import with_transient_model_messages, extend_transient_model_messages


@dataclass
class LoopRequest:
    student_id: str
    session_id: str
    task_id: str
    request_id: str
    message: str
    system_prompt: str
    tools: ToolRegistry
    seed_messages: list[dict[str, Any]] = field(default_factory=list)
    target: LearningTarget | None = None
    navigation: Any = None
    tool_state: dict[str, Any] = field(default_factory=dict)
    cancellation: Cancellation | None = None
    guard: Callable[[], None] | None = None
    publish_gate: Callable[[str, "LoopResult"], tuple[bool, str]] | None = None
    emit: Callable[[str, str, dict[str, Any] | None], None] | None = None
    max_exploration_rounds: int = 8
    max_settlement_rounds: int = 3
    max_parallel_calls: int = 15
    tool_timeout_seconds: float | None = 120
    round_max_tokens: int = 1200
    temperature: float = 0.2
    tool_choice: str | None = None


@dataclass
class LoopResult:
    final_text: str = ""
    completed: bool = False
    paused: bool = False
    pending_question: dict[str, Any] | None = None
    pending_tool_call_id: str | None = None
    messages: list[dict[str, Any]] = field(default_factory=list)
    rounds: int = 0
    exploration_rounds: int = 0
    settlement_rounds: int = 0
    tool_steps: int = 0
    sources: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    error: str = ""
    events: list[dict[str, Any]] = field(default_factory=list)
    protocol_version: int = 1

    def state(self) -> dict[str, Any]:
        """Serializable state for TaskService persistence."""
        return {
            "protocol_version": self.protocol_version,
            "messages": self.messages,
            "rounds": self.rounds,
            "exploration_rounds": self.exploration_rounds,
            "settlement_rounds": self.settlement_rounds,
            "tool_steps": self.tool_steps,
            "sources": self.sources,
            "pending_question": self.pending_question,
            "pending_tool_call_id": self.pending_tool_call_id,
            "target": self._target_dict(),
        }

    def _target_dict(self):
        if not hasattr(self, "_target") or self._target is None:
            return None
        target = self._target
        return {"target_id": target.target_id, "name": target.name,
                "source_scope": target.source_scope,
                "chapter_id": target.chapter_id, "section_id": target.section_id,
                "version": target.version, "reason": target.reason}


class LocalAgentLoop:
    def __init__(self, llm: LLMClient, *, max_round_tokens: int = 1200) -> None:
        self.llm = llm
        self.max_round_tokens = max_round_tokens

    def run(self, request: LoopRequest, *, resume_state: dict[str, Any] | None = None,
            answer: str = "") -> LoopResult:
        collector = EventCollector(request.emit)
        result = LoopResult()
        result._transient = []
        result._target = request.target
        try:
            messages = self._initial_messages(request, resume_state, answer, result)
            if resume_state:
                result.rounds = int(resume_state.get("rounds", 0))
                result.exploration_rounds = int(resume_state.get("exploration_rounds", 0))
                result.settlement_rounds = int(resume_state.get("settlement_rounds", 0))
                result.tool_steps = int(resume_state.get("tool_steps", 0))
                result.sources = list(resume_state.get("sources") or [])
                from knowledge.answer_media import model_message
                for source in result.sources:
                    anchor = source.get('location', {}).get('model_message_anchor')
                    image = model_message(source.get('image_refs', [])) if anchor else None
                    if image:
                        extend_transient_model_messages(result._transient, [{**image, '_after_tool_call_id': anchor}])
                collector("progress", "继续原任务", {"detail": "已恢复待回答的同一任务"})
            seen_sources = {str(source.get("source_id") or "")
                            for source in result.sources if source.get("source_id")}
            tool_context = ToolContext(
                student_id=request.student_id, session_id=request.session_id,
                task_id=request.task_id, request_id=request.request_id,
                knowledge_point=request.target.name if request.target else "",
                cancellation=request.cancellation, navigation=request.navigation,
                state={**dict(request.tool_state), "learning_target": request.target,
                       # A paused task may already contain retrieved sources.
                       # Continue numbering after them instead of reusing [1].
                       "source_offset": len(result.sources),
                       "seen_source_ids": seen_sources,
                       "max_sources": int(request.tool_state.get("max_sources", 24))},
                emit=collector,
            )
            outcome = self._loop(request, messages, result, tool_context, collector)
            result.events = collector.to_dicts()
            return outcome
        except CancelledError:
            result.events = collector.to_dicts()
            result.error = "cancelled"
            collector("error", "任务已取消", {"code": "cancelled"})
            return result
        except Exception as exc:
            result.events = collector.to_dicts()
            result.error = f"{type(exc).__name__}: {exc}"
            collector("error", "本次执行失败", {"code": "loop_failed"})
            return result

    def _initial_messages(self, request: LoopRequest, resume_state: dict | None,
                          answer: str, result: LoopResult) -> list[dict[str, Any]]:
        if resume_state:
            state = resume_state
            messages = deepcopy(state.get("messages") or [])
            pending_id = state.get("pending_tool_call_id") or ""
            pending = state.get("pending_question") or {}
            directive = format_user_reply(pending, answer)
            directive += ("\n\n[ask_user 已回答。请使用这些回答继续学生最初的任务，"
                          "不要只回复确认，也不要重新执行已回答的工具。]")
            if not pending_id or not substitute_answer(messages, pending_id, directive):
                raise ValueError("恢复状态缺少待回答的工具消息")
            result.pending_question = pending
            result.pending_tool_call_id = pending_id
            return messages
        messages = [{"role": "system", "content": request.system_prompt}]
        messages.extend(deepcopy(request.seed_messages))
        messages.append({"role": "user", "content": request.message})
        return messages

    def _loop(self, request: LoopRequest, messages: list[dict[str, Any]],
              result: LoopResult, context: ToolContext,
              collector: EventCollector) -> LoopResult:
        exploration_budget = max(1, request.max_exploration_rounds)
        settlement_budget = max(0, request.max_settlement_rounds)
        repair_used = False
        no_tools_next = False
        while True:
            if request.cancellation is not None:
                request.cancellation.check()
            if request.guard is not None:
                request.guard()
            settling = result.exploration_rounds >= exploration_budget
            if settling and result.settlement_rounds >= settlement_budget:
                return self._forced_finish(request, messages, result, context, collector)
            collector("stage_start", "收尾" if settling else "探索",
                      {"round": result.rounds + 1})
            tools = [] if no_tools_next else request.tools.schemas()
            try:
                round_result = self.llm.chat_with_tools(
                    with_transient_model_messages(messages, result._transient), tools or [], temperature=request.temperature,
                    timeout=90,
                    max_tokens=request.round_max_tokens,
                    tool_choice=request.tool_choice if result.rounds == 0 else None,
                    **answer_kwargs(),
                )
            except LLMError as exc:
                if result.rounds == 0:
                    result.error = f"model_unavailable: {exc}"
                    collector("error", "模型暂时不可用", {"code": "model_unavailable"})
                    return result
                return self._forced_finish(request, messages, result, context, collector,
                                           reason=f"模型调用失败：{exc}")
            result.rounds += 1
            self._mark_pixels(result)
            if settling:
                result.settlement_rounds += 1
            else:
                result.exploration_rounds += 1
            for key, value in (round_result.usage or {}).items():
                result.usage[key] = result.usage.get(key, 0) + int(value)
            if round_result.finish_reason == 'length':
                retract()
                return self._error_result(result, messages, collector, 'incomplete_answer', '模型输出达到长度上限，未完成回答')
            if round_result.tool_calls:
                retract()
                messages.append({
                    "role": "assistant",
                    "content": round_result.text or "",
                    "tool_calls": [
                        {"id": call.id, "type": "function",
                         **({'extra_content': call.extra_content} if call.extra_content else {}),
                         "function": {"name": call.name,
                                      "arguments": call.raw_arguments or json.dumps(call.arguments, ensure_ascii=False)}}
                        for call in round_result.tool_calls
                    ],
                })
                dispatch = dispatch_tool_calls(
                    tool_calls=round_result.tool_calls, registry=request.tools,
                    context=context, max_calls=request.max_parallel_calls,
                    timeout_seconds=request.tool_timeout_seconds,
                )
                result.tool_steps += 1
                messages.extend(dispatch.tool_messages)
                extend_transient_model_messages(result._transient, dispatch.model_messages)
                result.sources.extend(dispatch.sources)
                context.state["source_offset"] = len(result.sources)
                if dispatch.sources:
                    collector("sources", "", {"sources": dispatch.sources})
                if dispatch.pause:
                    result.paused = True
                    result.pending_question = (dispatch.pause_payload or {}).get("ask_user")
                    result.pending_tool_call_id = dispatch.pause_tool_call_id
                    result.messages = messages
                    collector("wait_for_input", "等待学生回答", {
                        "ask_user": result.pending_question,
                        "tool_call_id": result.pending_tool_call_id,
                    })
                    return result
                if dispatch.terminate:
                    result.final_text = str((dispatch.terminate_payload or {}).get("content") or "")
                    result.completed = True
                    result.pending_question = None
                    result.pending_tool_call_id = None
                    result.messages = messages
                    collector("answer", result.final_text, {})
                    return result
                continue
            final_text = (round_result.text or "").strip()
            if not final_text:
                if result.rounds < exploration_budget + settlement_budget + 1:
                    messages.append({"role": "user", "content":
                        "上一轮没有给出面向学生的回答。请直接回答，或调用必要工具；不要只输出内部推理。"})
                    continue
                return self._error_result(result, messages, collector, "empty_answer",
                                          "模型没有返回可发布回答")
            if request.publish_gate is not None:
                checking()
                ok, reason = request.publish_gate(final_text, result)
                if not ok:
                    retrieved = any(call.get('function', {}).get('name') == 'retrieve_course'
                                    for row in messages if row.get('role') == 'assistant'
                                    for call in row.get('tool_calls', []))
                    if not repair_used and not retrieved and reason == '本轮没有可核验的教材来源，暂不发布正式回答。':
                        repair_used = True
                        messages.extend([{'role':'assistant','content':final_text},
                            {'role':'user','content':'本轮还未调用 retrieve_course。请先读取当前问题的教材原文，再完成讲解；历史不是本轮引用依据。'}])
                        collector('progress','补取教材依据',{'detail':reason})
                        continue
                    if not repair_used and any(token in (reason or "") for token in
                                               ("过长", "压缩", "字数", "超过", "引用格式", "格式无效", "尚未引用双方")):
                        repair_used = True
                        no_tools_next = True
                        messages.append({"role": "assistant", "content": final_text})
                        if any(token in (reason or "") for token in ("过长", "压缩", "字数", "超过")):
                            instruction = ("\n请在不新增事实、不改变引用编号和范围的前提下压缩重写，"
                                           "不要调用工具，直接给出修订后的完整回答。")
                            label = "压缩修订"
                        elif '尚未引用双方' in reason:
                            instruction = ('\n只使用已有原文重新组织回答，分别解释双方对象并在支持的结论旁标注各自引用；'
                                           '不能为了补编号硬贴不支持结论的引文，不新增事实或调用工具。')
                            label = '覆盖引用修订'
                        else:
                            instruction = ("\n请只修正引用格式，使用单独的 [n] 编号；"
                                           "不新增事实、不改变引用对应的来源，不要调用工具，"
                                           "直接给出修订后的完整回答。")
                            label = "引用修订"
                        messages.append({"role": "user", "content":
                            "上一版回答未通过课程核验：" + (reason or "格式不符合要求")
                            + instruction})
                        collector("progress", label, {"detail": reason or ""})
                        continue
                    result.final_text = reason or "本次回答未通过课程核验，暂不发布。"
                    result.error = "quality_rejected"
                    result.messages = messages
                    collector("error", result.final_text, {"code": "quality_rejected"})
                    return result
            messages.append({"role": "assistant", "content": final_text})
            result.final_text = final_text
            result.completed = True
            result.pending_question = None
            result.pending_tool_call_id = None
            result.messages = messages
            collector("answer", final_text, {})
            collector("done", "", {"rounds": result.rounds, "tool_steps": result.tool_steps})
            return result

    def _forced_finish(self, request: LoopRequest, messages: list[dict[str, Any]],
                       result: LoopResult, context: ToolContext,
                       collector: EventCollector, reason: str = "") -> LoopResult:
        if request.cancellation is not None:
            request.cancellation.check()
        if request.guard is not None:
            request.guard()
        instruction = ("工具/探索预算已用尽。现在停止调用工具，只基于已经取得的材料给出最终回答；"
                       "明确说明仍不确定的部分，不要声称未执行的工具成功。")
        if reason:
            instruction += "\n" + reason
        messages.append({"role": "user", "content": instruction})
        try:
            round_result = self.llm.chat_with_tools(
                with_transient_model_messages(messages, result._transient), [], temperature=request.temperature,
                timeout=90,
                max_tokens=request.round_max_tokens, **answer_kwargs())
        except LLMError as exc:
            return self._error_result(result, messages, collector, "forced_finish_failed",
                                      f"收尾回答失败：{exc}")
        result.rounds += 1
        self._mark_pixels(result)
        if result.exploration_rounds >= request.max_exploration_rounds:
            result.settlement_rounds += 1
        for key, value in (round_result.usage or {}).items():
            result.usage[key] = result.usage.get(key, 0) + int(value)
        text = (round_result.text or "").strip()
        if round_result.tool_calls or round_result.finish_reason == 'tool_calls':
            retract()
            return self._error_result(result, messages, collector, 'unfinished_tool_round',
                                      '收尾阶段仍返回工具调用，未完成回答')
        if round_result.finish_reason == 'length':
            retract()
            return self._error_result(result, messages, collector, 'incomplete_answer', '模型输出达到长度上限，未完成回答')
        if not text:
            return self._error_result(result, messages, collector, "empty_answer",
                                      "预算用尽后模型仍未给出回答")
        if request.publish_gate is not None:
            checking()
            ok, gate_reason = request.publish_gate(text, result)
            if not ok:
                result.final_text = gate_reason or "本次回答未通过课程核验，暂不发布。"
                result.error = "quality_rejected"
                result.messages = messages
                collector("error", result.final_text, {"code": "quality_rejected"})
                return result
        result.final_text = text
        result.completed = True
        result.pending_question = None
        result.pending_tool_call_id = None
        messages.append({"role": "assistant", "content": text})
        result.messages = messages
        collector("answer", text, {})
        collector("done", "", {"rounds": result.rounds, "tool_steps": result.tool_steps,
                               "forced_finish": True})
        return result

    @staticmethod
    def _mark_pixels(result):
        received = {id for message in result._transient for id in message.get('_media_ids', [])}
        for source in result.sources:
            for image in source.get('image_refs', []):
                if image['id'] in received:
                    image['model_saw_pixels'] = True

    @staticmethod
    def _error_result(result: LoopResult, messages: list[dict[str, Any]],
                      collector: EventCollector, code: str, message: str) -> LoopResult:
        result.error = code
        result.final_text = message
        result.pending_question = None
        result.pending_tool_call_id = None
        result.messages = messages
        collector("error", message, {"code": code})
        return result


__all__ = ["LocalAgentLoop", "LoopRequest", "LoopResult"]
