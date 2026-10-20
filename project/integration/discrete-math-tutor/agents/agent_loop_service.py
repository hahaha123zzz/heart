"""Wire the Q3 local loop into the project's task identity and page result shape."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Callable

from agents.agent_loop import LocalAgentLoop, LoopRequest, LoopResult
from agents.loop_prompts import build_loop_system_prompt
from agents.q3_navigation import (
    CallbackNavigator, LearningTarget, NavigationDecision, StubLearningNavigator,
    source_from_chunk,
)
from agents.q3_tools import build_registry
from agents.task_cancellation import register, release
from knowledge.citation_guard import citation_issues
from models.task_context import TaskContext
from agents.teaching_planner import TeachingPlan


def _target_from_context(context: TaskContext) -> LearningTarget:
    # Q2's TaskService resolves chapter/next-topic requests before the model
    # runs.  Use that authoritative target instead of re-parsing the message
    # or falling back to the reader's current chapter.
    navigation = getattr(context, "course_navigation", None)
    if isinstance(navigation, dict) and navigation.get("status") == "ready":
        point = str(navigation.get("title") or context.knowledge_point or "当前学习目标").strip()
        return LearningTarget(
            target_id=str(navigation.get("id") or f"kp:{point}"),
            name=point,
            chapter_id=navigation.get("chapter_id"),
            section_id=navigation.get("section_id"),
            version=str(navigation.get("version") or ""),
            reason="Q2 目录导航已解析",
        )
    point = (context.knowledge_point or "当前学习目标").strip()
    object_row = next((obj for obj in context.objects if obj.kind == "section"), None)
    return LearningTarget(
        target_id=f"kp:{point}",
        name=point,
        chapter_id=object_row.chapter_id if object_row else None,
        section_id=object_row.section_id if object_row else None,
        reason="页面当前目标",
    )


def _target_from_state(state: dict[str, Any] | None) -> LearningTarget | None:
    row = (state or {}).get("target")
    if not isinstance(row, dict) or not row.get("target_id"):
        return None
    return LearningTarget(
        target_id=str(row.get("target_id")),
        name=str(row.get("name") or row.get("target_id")),
        chapter_id=row.get("chapter_id"),
        section_id=row.get("section_id"),
        version=str(row.get("version") or ""),
        reason=str(row.get("reason") or "恢复的任务目标"),
    )


def _resume_state(previous: dict[str, Any] | None) -> dict[str, Any] | None:
    state = ((previous or {}).get("context") or {}).get("loop_state")
    if isinstance(state, dict) and state.get("pending_tool_call_id"):
        return state
    return None


def _default_navigator(target: LearningTarget | None,
                       host_navigation: dict[str, Any] | None = None) -> Any:
    """Use Q2 local retrieval only when explicitly enabled.

    When the host already resolved a chapter/next-topic request, the target is
    authoritative: do not turn "继续下一个知识点" back into a clarification or
    ignore the Q2 cursor.  ``stub`` remains the safe default for callers that
    do not enable local retrieval.
    """
    if (isinstance(host_navigation, dict)
            and host_navigation.get("status") == "ready" and target is not None):
        def resolve_host(**_kwargs):
            return NavigationDecision("teach", target, reason="Q2 已解析当前学习目标")

        def search_host(*, target: LearningTarget, query: str, limit: int,
                        preferred_types: tuple[str, ...] = ()):
            # Q2's resolved cursor identifies one textbook block. Read that
            # block first so a generic query cannot pull the answer into a
            # different part of the same section.
            from knowledge.course_navigation import read_target
            exact = read_target({"id": target.target_id, "version": target.version})
            if exact:
                return [source_from_chunk(chunk, index)
                        for index, chunk in enumerate(exact[:limit])]
            from knowledge.local_rag.course_retrieval import retrieve
            candidates = retrieve(f"{target.name} {query}".strip(),
                                  limit=max(12, limit * 3),
                                  preferred_types=preferred_types)
            scoped = [chunk for chunk in candidates
                      if target.chapter_id is not None
                      and getattr(chunk, "chapter_id", None) == target.chapter_id
                      and (target.section_id is None
                           or getattr(chunk, "section_id", None) == target.section_id)]
            if not scoped:
                # The section may not have a matching semantic chunk (for
                # example a heading-only target).  Read the resolved unit so
                # the answer still stays inside the selected knowledge point.
                scoped = read_target({"id": target.target_id, "version": target.version})
            return [source_from_chunk(chunk, index)
                    for index, chunk in enumerate(scoped[:limit])]

        return CallbackNavigator(resolve_fn=resolve_host, search_fn=search_host)

    mode = os.getenv("Q3_RETRIEVAL_MODE", "stub").strip().lower()
    if mode in ("local", "q2", "local_llamaindex"):
        try:
            from knowledge.local_rag.course_retrieval import retrieve

            def search(*, target: LearningTarget, query: str, limit: int,
                       preferred_types: tuple[str, ...] = ()):
                chunks = retrieve(f"{target.name} {query}".strip(), limit=limit,
                                  preferred_types=preferred_types)
                return [source_from_chunk(chunk, index) for index, chunk in enumerate(chunks)]

            return CallbackNavigator(search_fn=search)
        except Exception:
            # The caller/report must see the degraded state; do not silently
            # claim Q2 retrieval ran.
            return StubLearningNavigator(target=target, sources=[])
    return StubLearningNavigator(target=target, sources=[])


def _citation_format_issues(text: str) -> str:
    """Reject bracket text that starts like a citation but is not [n]."""
    for match in re.finditer(r"\[([^\]\n]{1,80})\]", text):
        inner = match.group(1).strip()
        if not inner or not inner[0].isdigit():
            continue
        # The page and the citation publisher both map one [n] to one
        # source_index.  Ranges such as [1-3] would pass this gate but render
        # no cards, so only single numeric citations are accepted.
        if re.fullmatch(r"\d+", inner):
            continue
        return f"引用格式无效：{match.group(0)[:60]}"
    return ""


def _excerpts(sources: list[dict[str, Any]]) -> str:
    lines = []
    for position, source in enumerate(sources, 1):
        index = int(source.get("index") or position)
        header = str(source.get("document_id") or "")
        if source.get("page"):
            header += f"｜第{source['page']}页"
        lines.append(f"[{index}] {header}\n{source.get('text') or ''}")
    return "\n".join(lines)


def _publish_gate(orchestrator: Any, request: Any, target: LearningTarget):
    def gate(text: str, result: LoopResult) -> tuple[bool, str]:
        if not text.strip():
            return False, "模型没有返回可发布回答。"
        if not result.sources:
            return False, "本轮没有可核验的教材来源，暂不发布正式回答。"
        excerpts = _excerpts(result.sources)
        issues = citation_issues(text, excerpts)
        if issues:
            return False, "本次引用未通过核验：" + "；".join(issues)
        format_issue = _citation_format_issues(text)
        if format_issue:
            return False, format_issue
        if not re.search(r"\[\d+\]", text):
            return False, "回答未标注本轮教材引用编号，暂不发布。"
        checker = getattr(orchestrator, "quality_checker", None)
        memory = getattr(orchestrator, "memory", None)
        if checker is None or memory is None:
            return True, ""
        try:
            state = memory.get_state(request.student_id, target.name)
            plan = TeachingPlan(goal=f"回答{target.name}", strategy="scaffolding",
                                action="explain", difficulty="medium")
            maximum = int(os.getenv("Q3_REPLY_MAXIMUM", "800"))
            quality = checker.check(text, state, plan, request.message,
                                    context={"loop_sources": result.sources,
                                             "agent_loop": True,
                                             "reply_maximum_override": max(600, maximum)},
                                    textbook_excerpts=excerpts)
            if not quality.passed or quality.issues:
                return False, "本次回答未通过教材核对：" + "；".join(quality.issues or [])
        except Exception as exc:
            return False, f"教材核验未完成：{type(exc).__name__}"
        return True, ""
    return gate


def _release_binding() -> dict[str, Any] | None:
    try:
        from knowledge.course_release import binding
        return binding()
    except Exception:
        return None


def _map_result(result: LoopResult, target: LearningTarget,
                conversation_id: int | None = None) -> dict[str, Any]:
    base = {
        "loop_summary": {
            "protocol_version": result.protocol_version,
            "rounds": result.rounds,
            "settlement_rounds": result.settlement_rounds,
            "tool_steps": result.tool_steps,
            "usage": result.usage,
            "target": target.target_id,
        },
        "loop_events": result.events,
        "knowledge_point": target.name,
        "routing": {"status": "ok", "intent": "continue", "student_move": "question",
                    "confidence": 1.0, "needs_context": True,
                    "reason": "Q3 本地工具循环"},
    }
    if conversation_id is not None:
        # TaskService uses the same committed marker for navigation cursor
        # persistence; an answered loop turn must not skip it.
        base["memory_commit"] = {"status": "committed",
                                 "conversation_id": conversation_id}
    if result.paused:
        questions = (result.pending_question or {}).get("questions") or []
        prompt = str(questions[0].get("prompt") if questions else "还需要补充信息。")
        options = []
        if len(questions) == 1:
            options = [{"id": f"q1:{index}", "label": option.get("label") or "",
                        "description": option.get("description") or ""}
                       for index, option in enumerate(questions[0].get("options") or [])
                       if option.get("label")]
        return {
            **base,
            "reply": prompt,
            "answer_status": "awaiting_clarification",
            "clarification": {
                "mode": "ask_user",
                "ask_user": result.pending_question,
                "questions": questions,
                "options": options,
            },
            "loop_paused": True,
            "loop_state": result.state(),
            "step_advanced": False,
        }
    if result.error == "cancelled":
        return {**base, "reply": "本次问题已取消。", "answer_status": "task_cancelled",
                "step_advanced": False, "loop_state": result.state()}
    if result.error == "quality_rejected":
        return {
            **base,
            "reply": result.final_text or "本次回答未通过课程核验，暂不发布。",
            "answer_status": "quality_rejected",
            "quality": {"passed": False, "issues": [result.final_text]},
            "sources": result.sources,
            "step_advanced": False,
            "loop_state": result.state(),
        }
    if not result.completed:
        return {
            **base,
            "reply": "本次执行未完成，请重试或缩小问题范围。",
            "answer_status": "loop_failed",
            "loop_error": result.error,
            "sources": result.sources,
            "step_advanced": False,
            "loop_state": result.state(),
        }
    textbook_sources = []
    for position, source in enumerate(result.sources, 1):
        label = str((source.get("location") or {}).get("source_file")
                    or source.get("document_id") or "教材")
        if source.get("page"):
            label += f"（第{source['page']}页）"
        textbook_sources.append(label)
    # Publish only evidence the answer actually cites.  The front-end maps
    # [n] to source_index n-1, so keep the original global number instead of
    # compacting it.  Uncited retrieval hits must not become citation cards.
    cited = {int(value) for value in re.findall(r"\[(\d+)\]", result.final_text)}
    by_index = {int(source.get("index") or position): source
                for position, source in enumerate(result.sources, 1)}
    release = _release_binding()
    pdf_references = []
    for citation_index in sorted(cited):
        source = by_index.get(citation_index)
        if source is None:
            continue
        reference = {
            "source_index": citation_index - 1,
            "label": "Q3 教材检索",
            "selection_ref": {
                "document_id": source.get("document_id") or "",
                "version": source.get("version") or "",
                "kind": "text",
                "page": source.get("page"),
                "chapter_id": source.get("chapter_id"),
                "section_id": source.get("section_id"),
                "section_title": target.name,
                "source": ((source.get("location") or {}).get("source_file")
                           or source.get("document_id") or ""),
                "text": source.get("text") or "",
                "image_refs": source.get("image_refs") or [],
            },
            "evidence": {
                "evidence_id": source.get("source_id") or "",
                "quote": (source.get("quote") or source.get("text") or "")[:500],
                "document_id": source.get("document_id") or "",
                "document_version": source.get("version") or "",
                "location_status": "page" if source.get("page") else "section",
                "selections": [],
            },
        }
        if release:
            reference["selection_ref"].update({
                "textbook_release": release.get("release_id"),
                "release_status": release.get("status"),
            })
            reference["evidence"].update({
                "textbook_release": release.get("release_id"),
                "release_status": release.get("status"),
                "release_ready": release.get("ready"),
            })
        pdf_references.append(reference)
    return {
        **base,
        "reply": result.final_text,
        "answer_status": "answered",
        "conversation_id": conversation_id,
        "textbook_sources": textbook_sources,
        "pdf_references": pdf_references,
        "sources": result.sources,
        "step_advanced": False,
        "loop_state": result.state(),
    }


def run_agent_loop_turn(*, orchestrator: Any, request: Any, context: TaskContext,
                        resolved: Any = None, intercept: Any = None,
                        guard: Callable[[], None] | None = None,
                        progress: Callable[[str, str, str], None] | None = None,
                        previous: dict[str, Any] | None = None,
                        navigator: Any = None,
                        publish_gate: Callable[[str, LoopResult], tuple[bool, str]] | None = None,
                        llm: Any = None) -> dict[str, Any]:
    """Run one project task turn through the local loop.

    The caller (``TaskService``) already claimed the task and owns its
    revision/idempotency; this function only executes the turn.
    """
    resume_state = _resume_state(previous)
    current_target = _target_from_state(resume_state) or _target_from_context(context)
    navigation = navigator or _default_navigator(
        current_target, getattr(context, "course_navigation", None))
    decision: NavigationDecision = navigation.resolve(
        message=request.message, student_id=request.student_id,
        session_id=request.session_id, current_target=current_target,
        context=context,
    )
    if decision.action == "clarify" and decision.missing:
        return {
            "reply": "需要先确定本轮学习目标：当前没有可用的课程路径或明确的下一目标，"
                     "因此不会用“下一知识点”原句直接检索教材。",
            "answer_status": "navigation_required",
            "step_advanced": False,
            "navigation": {"action": decision.action, "missing": list(decision.missing),
                           "reason": decision.reason},
        }
    target = decision.target or current_target
    root = Path(__file__).resolve().parents[1]
    skills_root = root / "visualization" / "skills"
    task_key = re.sub(r"[^A-Za-z0-9_.-]+", "_",
                      request.task_id or request.request_id or "turn")[:80]
    workspace_root = Path(os.getenv("Q3_WORKSPACE_ROOT") or
                          (root / ".runtime" / "q3-workspaces" / task_key)).resolve()
    allow_workspace = os.getenv("Q3_ENABLE_WORKSPACE_TOOLS", "0").strip() == "1"
    if allow_workspace:
        workspace_root.mkdir(parents=True, exist_ok=True)
    registry = build_registry(
        workspace_root=workspace_root,
        skills_root=skills_root,
        allow_workspace=allow_workspace,
        allow_skills=skills_root.is_dir(),
    )
    system_prompt = build_loop_system_prompt(target=target, definitions=registry.definitions())
    cancellation = register(request.task_id or request.request_id)

    def emit(event_type: str, message: str,
             detail: str | dict[str, Any] | None = None) -> None:
        # EventCollector forwards a short string; some callers pass metadata.
        # Accept both so the page progress callback cannot fail the turn.
        if progress is None:
            return
        if isinstance(detail, dict):
            text = detail.get("detail") or message or ""
        else:
            text = detail or message or ""
        progress("loop-" + event_type, event_type, str(text)[:300])

    loop = LocalAgentLoop(llm or orchestrator.llm)
    result = loop.run(
        LoopRequest(
            student_id=request.student_id, session_id=request.session_id,
            task_id=request.task_id or request.request_id,
            request_id=request.request_id or "",
            message=request.message, system_prompt=system_prompt, tools=registry,
            seed_messages=list(context.history or []), target=target,
            navigation=navigation, cancellation=cancellation, guard=guard,
            tool_state={"workspace_root": str(workspace_root),
                        "skills_root": str(skills_root), "deferred_loader": None},
            publish_gate=publish_gate or _publish_gate(orchestrator, request, target),
            emit=emit, tool_timeout_seconds=120, max_exploration_rounds=4,
        ),
        resume_state=resume_state,
        answer=str((previous or {}).get("_resume_answer") or ""),
    )
    conversation_id = None
    mapped = _map_result(result, target)
    if result.completed:
        memory = getattr(orchestrator, "memory", None)
        if memory is not None:
            try:
                _, epoch = memory.read_version(request.student_id, target.name)
                user_message = (str((previous or {}).get("_resume_answer") or "")
                                if resume_state else request.message)
                # Persist the same citation cards the page just rendered, so a
                # refresh/reload can restore body numbering and source cards.
                stored_reference = {
                    "pdf_references": mapped.get("pdf_references", []),
                    "textbook_sources": mapped.get("textbook_sources", []),
                    "chapter_id": target.chapter_id,
                    "section_id": target.section_id,
                    "section_title": target.name,
                }
                conversation_id = memory.append_exchange(
                    request.student_id, user_message, result.final_text,
                    selection_ref=stored_reference
                    if stored_reference["pdf_references"] or stored_reference["textbook_sources"]
                    else None,
                    expected_epoch=epoch, expected_point=target.name, task_guard=guard)
                if conversation_id is False:
                    release(request.task_id or request.request_id)
                    return {
                        "reply": "这个知识点的学习记忆已被删除，本次回答未保存，请重新提问。",
                        "answer_status": "memory_deleted",
                        "step_advanced": False,
                        "loop_state": result.state(),
                    }
                mapped["conversation_id"] = conversation_id
                mapped["memory_commit"] = {"status": "committed",
                                          "conversation_id": conversation_id}
            except Exception as exc:
                release(request.task_id or request.request_id)
                return {
                    "reply": "本次回答已生成，但学习记录保存失败，未作为正式回答发布。",
                    "answer_status": "loop_failed",
                    "loop_error": f"memory_save_failed: {type(exc).__name__}",
                    "step_advanced": False,
                    "loop_state": result.state(),
                }
    if not result.paused:
        release(request.task_id or request.request_id)
    navigation_row = getattr(context, "course_navigation", None)
    if isinstance(navigation_row, dict) and navigation_row.get("status") == "ready":
        explained = (mapped.get("answer_status") == "answered"
                     and mapped.get("memory_commit", {}).get("status") == "committed")
        mapped["course_navigation"] = dict(navigation_row, explained=explained)
    return mapped


__all__ = ["run_agent_loop_turn"]
