"""将已校验的宿主任务绑定到同一个 UnifiedContext，不序列化私有状态。"""
from __future__ import annotations

from copy import deepcopy
import json
from agents.context_runtime.context import UnifiedContext
from agents.context_runtime.context_budget import LLMRequestSnapshot, build_context_budget
from agents.context_runtime.model_history import normalize_model_turn


def assemble_turn(task, history=None):
    context = task._unified_context
    if context is None:
        context = UnifiedContext(language="zh", active_capability="chat")
        task._unified_context = context
    context.session_id = task.session_id
    context.user_message = task.message
    context.conversation_history = deepcopy(task.history)
    context.runtime.turn_id = task.task_id or task.request_id or ""
    if history is not None:
        context.runtime.model_history = deepcopy(history.model_history)
        context.runtime.previous_model_turn = deepcopy(history.previous_model_turn)
        context.metadata.update(history_token_count=history.token_count, history_budget=history.budget,
                                summary_up_to_msg_id=history.summary_up_to_msg_id)
    context.metadata["conversation_summary"] = task.history_summary
    context.metadata["learner_profile_prompt"] = json.dumps({
        "known_points": task.known_points, "preferences": task.preferences}, ensure_ascii=False)
    if task.session_study_plan:
        context.learning_journal_context = json.dumps({key: value for key, value in task.session_study_plan.items()
            if key not in ("student_id", "session_id")}, ensure_ascii=False)
    context.sidebar_context = "\n\n".join(obj.text for obj in task.objects
        if obj.kind in ("pdf_selection", "exercise_part"))
    host = context.extension("heart")
    host.update(student_id=task.student_id, session_id=task.session_id,
                task_id=task.task_id, task_revision=task.task_revision, task=task)
    return context


def record_request(context, messages, tools, *, model="", max_tokens=None):
    host = context.extension("heart")
    context.metadata["context_budget"] = build_context_budget(
        blocks=host.get("prompt_blocks", []),
        request=LLMRequestSnapshot(messages=messages, tool_schemas=tools),
        model=model, max_tokens=max_tokens)


def finish_turn(context, result, *, published=False):
    context.interaction.end_loop = bool(result.completed)
    context.capability_output.agent_output = result.final_text if result.completed else ""
    context.capability_output.answer_published = bool(result.completed and published)
    messages = deepcopy(result.messages)
    system = messages.pop(0)["content"] if messages and messages[0].get("role") == "system" else ""
    start = max(0, result.model_turn_start - (1 if system else 0))
    context.runtime.model_turn = normalize_model_turn({"version": 1, "system": system, "messages": messages[start:]})


def render_turn_prompt(context, system_prompt):
    from agents.context_runtime.prompt_blocks import LoopPromptAssembler
    from agents.context_runtime.protocol import PromptBlock
    host = context.extension("heart")
    base = host.get("base_prompt", "")
    foundation = list(host.get("prompt_foundation", []))
    extra = system_prompt[len(base):] if base and system_prompt.startswith(base) else system_prompt
    if extra.strip():
        foundation.append(PromptBlock("host_turn_policy", extra))
    class TeachingPromptAssembler(LoopPromptAssembler):
        def foundation_blocks(self, context):
            return [*foundation, PromptBlock("runtime_context", self._runtime_context_block())]
    assembler = TeachingPromptAssembler(prompts={}, language=context.language)
    blocks = assembler.blocks(context=context, tool_manifest="", include_tool_manifest=False)
    host["prompt_blocks"] = blocks
    return assembler.render(blocks)


def retained_model_turn(state):
    from agents.adaptive_tutoring import redact_protocol
    safe = redact_protocol(state)
    messages = safe.get("messages") or []
    start = max(0, int(safe.get("model_turn_start", 1)))
    system = messages[0].get("content", "") if messages and messages[0].get("role") == "system" else ""
    return normalize_model_turn({"version": 1, "system": system, "messages": messages[start:]})
