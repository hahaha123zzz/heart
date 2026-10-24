"""Wire the Q3 local loop into the project's task identity and page result shape."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Callable

from agents.agent_loop import LocalAgentLoop, LoopRequest, LoopResult
from agents.loop_prompts import build_loop_system_prompt
from agents.reply_budget import reply_budget
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
        source_scope=dict(row.get('source_scope') or {}),
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
            is_exact = bool(re.fullmatch(r'ch\d+:s\d+:b\d+', target.target_id))
            exact = read_target({"id": target.target_id, "version": target.version}) if is_exact else []
            if exact:
                return [source_from_chunk(chunk, index)
                        for index, chunk in enumerate(exact[:limit])]
            from knowledge.local_rag.course_retrieval import retrieve
            candidates = retrieve(f"{target.name} {query}".strip(),
                                  limit=max(12, limit * 3),
                                  preferred_types=preferred_types)
            scoped = [chunk for chunk in candidates
                      if (target.chapter_id is None
                          or getattr(chunk, "chapter_id", None) == target.chapter_id)
                      and (target.section_id is None
                           or getattr(chunk, "section_id", None) == target.section_id)]
            if not scoped and is_exact:
                # The section may not have a matching semantic chunk (for
                # example a heading-only target).  Read the resolved unit so
                # the answer still stays inside the selected knowledge point.
                scoped = read_target({"id": target.target_id, "version": target.version})
            return [source_from_chunk(chunk, index)
                    for index, chunk in enumerate(scoped[:limit])]

        return CallbackNavigator(resolve_fn=resolve_host, search_fn=search_host)

    mode = os.getenv("Q3_RETRIEVAL_MODE", "stub").strip().lower()
    if mode in ("local", "q2", "local_llamaindex"):
        def search(*, target: LearningTarget, query: str, limit: int,
                       preferred_types: tuple[str, ...] = ()):
                from knowledge.local_rag.course_retrieval import retrieve
                chunks = retrieve(f"{target.name} {query}".strip(), limit=limit,
                                  preferred_types=preferred_types)
                return [source_from_chunk(chunk, index) for index, chunk in enumerate(chunks)]
        return CallbackNavigator(search_fn=search)
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


def _publish_gate(orchestrator: Any, request: Any, target: LearningTarget, navigation=None, teaching=None, selection_input=None):
    def gate(text: str, result: LoopResult) -> tuple[bool, str]:
        if not text.strip():
            return False, "模型没有返回可发布回答。"
        if selection_input is not None:
            passed, reason = selection_input.gate(text)
            if not passed:
                return False, reason
        if teaching is not None:
            passed, reason = teaching.gate(text)
            if not passed:
                return False, reason
        if not result.sources:
            return False, "本轮没有可核验的教材来源，暂不发布正式回答。"
        from agents.course_search import explicit_chapters
        required = explicit_chapters(request.message)
        missing = required - {source.get('chapter_id') for source in result.sources}
        partial = getattr(navigation, 'coverage_report', {}).get('status') == 'partial'
        if len(required) > 1 and missing and not partial:
            return False, '跨章问题缺少原文依据：' + '、'.join(f'第{chapter}章' for chapter in sorted(missing))
        coverage = getattr(navigation, 'coverage_report', {})
        if coverage.get('status') == 'covered':
            cited = {int(value) for value in re.findall(r'\[(\d+)\]', text)}
            supported = {item for position, source in enumerate(result.sources, 1)
                         if int(source.get('index') or position) in cited
                         for item in source.get('location', {}).get('retrieval_requirements', [])}
            if set(coverage.get('covered', [])) - supported:
                return False, '回答尚未引用双方对象的相关原文；请保留每方实际支持结论的引用，不能只引用其中一方。'
        evidence = [source.get('location', {}).get('evidence') for source in result.sources]
        if any(evidence):
            if not all(evidence):
                return False, '本轮混入未经原文核验的来源，暂不发布。'
            try:
                from knowledge.grounded_citations import EvidenceBundle
                from knowledge.lightrag.retrieval import as_textbook_chunk
                bundle = EvidenceBundle([as_textbook_chunk(s) for s in result.sources], evidence, [])
                body, sources, references = bundle.publish(text)
                result._publication = {'reply': body, 'pdf_references': references,
                                       'textbook_sources': [f'{s.source} · {s.section}' for s in sources]}
            except ValueError as exc:
                return False, '本次原文发布核验失败：' + str(exc)
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
            if selection_input is not None:
                selection_input.execution.align(plan)
            maximum = int(os.getenv("Q3_REPLY_MAXIMUM", "800"))
            from knowledge.answer_media import current_media
            refs = [image for source in result.sources for image in source.get('image_refs', [])
                    if image.get('model_saw_pixels')]
            checked_media = current_media(refs)
            quality = checker.check(text, state, plan, request.message,
                                    context={"loop_sources": result.sources,
                                             "agent_loop": True,
                                             "adaptive_teaching": teaching.public() if teaching else None,
                                             "selection_target": ({"id": target.target_id,
                                                  "text": selection_input.selected_text} if selection_input else None),
                                             "reply_maximum_override": max(600, maximum, reply_budget(request.message).maximum)},
                                    textbook_excerpts=excerpts,
                                    **({'task_execution': selection_input.execution} if selection_input else {}),
                                    **({'figure_images': [f.path for _, f in checked_media]} if checked_media else {}))
            if not quality.passed or quality.issues:
                return False, "本次回答未通过教材核对：" + "；".join(quality.issues or [])
            for image, _ in checked_media:
                image['visual_quality_checked'] = True
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
                        llm: Any = None, q5: Any = None,
                        visualization_jobs: list | None = None) -> dict[str, Any]:
    """Run one project task turn through the local loop.

    The caller (``TaskService``) already claimed the task and owns its
    revision/idempotency; this function only executes the turn.
    """
    resume_state = _resume_state(previous)
    from agents.selection_loop import enabled as selection_loop_enabled, descriptor, SelectionLoopInput
    selection_input = None
    if selection_loop_enabled():
        if context.selection_scope is None and request.selection is not None and request.selection.kind == 'text':
            context.selection_scope = descriptor(request.selection)
        if context.selection_scope is not None:
            selection_input = SelectionLoopInput(context, resolved)
            host_guard = guard
            def selection_guard():
                if host_guard:
                    host_guard()
                selection_input.guard()
            guard = selection_guard
    current_target = _target_from_state(resume_state) or _target_from_context(context)
    q5_binding = None
    if q5 is not None and selection_input is None:
        try:
            q5_binding = q5.loop_binding()
        except (ValueError, RuntimeError):
            q5_binding = None
    if selection_input is not None:
        current_target = selection_input.target
        navigation = selection_input
    elif q5_binding:
        current_target = q5_binding["target"]
        from agents.q5_learning import Q5Navigator
        navigation = (CallbackNavigator(resolve_fn=lambda **_: NavigationDecision('teach',current_target))
                      if q5_binding.get('session_study') else Q5Navigator(q5.service, q5.scope, search_fn=q5.search))
    else:
        navigation = navigator or _default_navigator(
            current_target, getattr(context, "course_navigation", None))
    from agents.course_search import shared_search
    if selection_input is None:
        navigation = shared_search(navigation, message=request.message,
                                  llm=llm or orchestrator.llm, navigator=navigator)
    decision: NavigationDecision = navigation.resolve(
        message=request.message, student_id=request.student_id,
        session_id=request.session_id, current_target=current_target,
        context=context,
    )
    if decision.action == "clarify" and decision.missing:
        release(request.task_id or request.request_id)
        return {
            "reply": "需要先确定本轮学习目标：当前没有可用的课程路径或明确的下一目标，"
                     "因此不会用“下一知识点”原句直接检索教材。",
            "answer_status": "navigation_required",
            "step_advanced": False,
            "navigation": {"action": decision.action, "missing": list(decision.missing),
                           "reason": decision.reason},
        }
    target = decision.target or current_target
    from agents.adaptive_tutoring import enabled as tutoring_enabled, TeachingTurn, TeachingStepTool
    if guard:
        guard()
    teaching = TeachingTurn(context, request, llm or orchestrator.llm, target=target) if tutoring_enabled() else None
    initial_sources = teaching.sources if teaching else []
    if selection_input is not None:
        initial_sources = initial_sources or selection_input.initial_sources()
        if teaching and ('no_questions' in selection_input.execution.answer_constraints
                         or selection_input.execution.hint_only):
            teaching.state['allow_check'] = False
            teaching._sync()
    if guard:
        guard()
    from agents.course_search import explicit_chapters, question_interjection
    chapters = explicit_chapters(request.message)
    interjection = bool(len(chapters) > 1 or
        (q5_binding and question_interjection(request.message, target))
        or (teaching and teaching.interjection))
    root = Path(__file__).resolve().parents[1]
    skills_root = root / "visualization" / "skills"
    task_key = re.sub(r"[^A-Za-z0-9_.-]+", "_",
                      request.task_id or request.request_id or "turn")[:80]
    workspace_root = Path(os.getenv("Q3_WORKSPACE_ROOT") or
                          (root / ".runtime" / "q3-workspaces" / task_key)).resolve()
    allow_workspace = os.getenv("Q3_ENABLE_WORKSPACE_TOOLS", "0").strip() == "1"
    if allow_workspace:
        workspace_root.mkdir(parents=True, exist_ok=True)
    from knowledge.lightrag.q3_adapter import ContextualRetrieveCourseTool
    q5_tools = tuple((q5_binding or {}).get('tool_instances') or ())
    if interjection:
        q5_tools = tuple(tool for tool in q5_tools if tool.definition.name in ('mastery_status', 'mastery_paths'))
    registry = build_registry(
        workspace_root=workspace_root,
        skills_root=skills_root,
        allow_workspace=allow_workspace,
        allow_skills=skills_root.is_dir(),
        extra_tools=(*q5_tools, ContextualRetrieveCourseTool(),
                     *((TeachingStepTool(teaching),) if teaching else ())),
        extra_scopes=('learning:read',) if interjection else tuple((q5_binding or {}).get("scopes") or ()),
    )
    budget = reply_budget(request.message)
    system_prompt = build_loop_system_prompt(
        target=target, definitions=registry.definitions(),
        teaching_prompt=teaching.instructions() if teaching else "",
        verified_sources=initial_sources) + "\n" + budget.instructions()
    if selection_input is not None:
        system_prompt += '\n' + selection_input.instructions()
    if interjection:
        system_prompt += '\n本轮是插问，只回答学生当前问题；保留原学习目标，不记录本目标已讲解、掌握或推进路径。'
    system_prompt += '\n页面当前学习目标仅作学习位置参考；具体提问优先，不要把旧小节主题擅自追加到检索词。指定图号先调用 retrieve_course 读取该图及登记原文，不能只检索旧主题便要求学生上传已有原图。'
    if q5_binding and q5_binding.get('session_study'):
        import json
        snapshot={k:v for k,v in q5_binding['session_plan'].items() if k not in ('student_id','session_id')}
        from models.interaction_preferences import style_instructions
        system_prompt += '\n当前仍有效的已确认风格（旧快照的画像文案不能覆盖这里；本次明确的学习约束仍保留）：\n'+style_instructions(context.preferences)
        system_prompt += '\n以下是本次已确认活动快照，只执行当前活动的kind和完成标准，估算时间不代表真实用时。学生本轮插问优先且不推进。不要一次教完整份安排，不改变长期路径，不把懂了当掌握。practice_preference=none时禁止检查题和考试。optional_check活动若生成自测，明确标注AI生成、非教材原题、未正式评分。\n' + json.dumps(snapshot,ensure_ascii=False)

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

    round_tokens = max(1200, budget.max_tokens)
    tool_seconds = 120 * max(1, len(navigation.coverage.requirements)) if navigation.coverage else 120
    loop = LocalAgentLoop(llm or orchestrator.llm, max_round_tokens=round_tokens)
    cancellation = register(request.task_id or request.request_id)
    navigation.cancellation = cancellation
    if navigation.coverage is not None:
        navigation.coverage.cancellation = cancellation
    if navigation.backend is not None and hasattr(navigation.backend, 'cancellation'):
        navigation.backend.cancellation = cancellation
    restored_reply = teaching.restore_reply() if teaching else None
    if restored_reply is not None:
        # Only the exact persisted, revalidated formative question is replayed.
        # No new model text or textbook assertion bypasses the publish gate.
        if guard:
            guard()
        result = LoopResult(final_text=restored_reply, completed=True,
                            sources=teaching.sources)
        result._target = target
        emit("progress", "恢复原来的理解检查")
    else:
        result = loop.run(
            LoopRequest(
                student_id=request.student_id, session_id=request.session_id,
                task_id=request.task_id or request.request_id,
                request_id=request.request_id or "",
                message=request.message, system_prompt=system_prompt, tools=registry,
                round_max_tokens=round_tokens,
                seed_messages=([] if selection_input and selection_input.scope_changed
                               else list(context.history or [])), target=target,
                initial_sources=initial_sources,
                navigation=navigation, cancellation=cancellation, guard=guard,
                tool_state={"workspace_root": str(workspace_root),
                            "skills_root": str(skills_root), "deferred_loader": None,
                            **((q5_binding or {}).get("tool_state") or {})},
                publish_gate=publish_gate or _publish_gate(orchestrator, request, target, navigation, teaching, selection_input),
                emit=emit, tool_timeout_seconds=tool_seconds, max_exploration_rounds=4,
            ),
            resume_state=resume_state,
            answer=str((previous or {}).get("_resume_answer") or ""),
        )
    if not result.paused:
        # 超时后可能仍有只读检索线程；回合结束即停止其后续补查，不取消等待学生的任务。
        cancellation.cancel()
    conversation_id = None
    mapped = _map_result(result, target)
    if teaching and result.completed:
        teaching.commit_sources(result.sources)
        mapped["teaching"] = teaching.public()
    if teaching and mapped.get("loop_state"):
        from agents.adaptive_tutoring import redact_protocol
        mapped["loop_state"] = redact_protocol(mapped["loop_state"])
    if selection_input is not None:
        mapped['entrypoint'] = 'pdf_text_selection'
        mapped['selection_ref'] = selection_input.reference
        mapped['pdf_image_refs'] = selection_input.reference.get('image_refs', [])
    if result.completed:
        media = {}
        for source in result.sources:
            for image in source.get('image_refs', []):
                media[image['id']] = image
        mapped['image_refs'] = list(media.values())[:2]
    if result.completed and getattr(result, '_publication', None):
        mapped.update(result._publication)
    if result.completed:
        # Q5 状态提示不参与来源编号，也不覆盖已核验正文。
        if q5_binding:
            try:
                status_line = q5.status_line()
            except (ValueError, RuntimeError):
                status_line = ''
            if status_line:
                first, _, rest = mapped['reply'].partition('\n')
                if re.sub(r'[*_`\s]', '', first) == re.sub(r'[*_`\s]', '', status_line):
                    mapped['reply'] = rest.lstrip()
                mapped['reply'] = status_line + '\n\n' + mapped['reply']
        result.final_text = mapped['reply']
    mapped['retrieval_calls'] = navigation.calls
    mapped['retrieval_coverage'] = navigation.coverage_report
    mapped['retrieval_trace'] = navigation.trace
    mapped['backend_calls'] = list(getattr(navigation.backend, 'calls', []) or []) if navigation.backend else []
    mapped['learning_interjection'] = interjection or restored_reply is not None or selection_input is not None
    if restored_reply is not None:
        mapped['publication_mode'] = 'saved_formative_question'
    if (selection_input is not None and result.completed and restored_reply is None
            and not (teaching and teaching.progress.pending_question)):
        # Preserve the selected-text pipeline's optional diagram integration.
        # Never build an answer-revealing diagram while a check awaits an answer.
        from knowledge.course_config import PSYCHOLOGY
        if PSYCHOLOGY and os.getenv('VISUALIZATION_ON_DEMAND', '0') == '1':
            from visualization.on_demand import build_guide, permitted
            if permitted(request.message, selection_input.execution):
                try:
                    from knowledge.lightrag.retrieval import as_textbook_chunk
                    guide = build_guide(orchestrator.llm, request.message, mapped['reply'],
                        [as_textbook_chunk(s) for s in result.sources], selection_input.execution,
                        student_id=request.student_id, turn_id=request.task_id or request.request_id,
                        references=mapped.get('pdf_references', []), progress=progress,
                        deferred=visualization_jobs)
                    if guide:
                        mapped['guided_visualization'] = guide
                except (ValueError, OSError, KeyError, RuntimeError):
                    pass
    if result.completed and navigation.coverage_report.get('status') == 'partial':
        gaps = '、'.join(row['query'] for row in navigation.coverage_report['missing'])
        mapped['reply'] = f'本次仅回答已有原文支持的部分；尚缺“{gaps}”的可靠教材证据，无法完整说明双方联系。\n\n' + mapped['reply']
        result.final_text = mapped['reply']
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
                    "image_refs": mapped.get('image_refs', []),
                    "session_study_plan": getattr(context,'session_study_plan',None),
                }
                if selection_input is not None:
                    stored_reference = {**selection_input.reference, **stored_reference}
                    if mapped.get('guided_visualization'):
                        stored_reference['guided_visualization'] = mapped['guided_visualization']
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
                        "loop_state": mapped.get("loop_state"),
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
                    "loop_state": mapped.get("loop_state"),
                }
    if not result.paused:
        release(request.task_id or request.request_id)
    navigation_row = getattr(context, "course_navigation", None)
    if isinstance(navigation_row, dict) and navigation_row.get("status") == "ready":
        explained = (not mapped.get('learning_interjection') and mapped.get("answer_status") == "answered"
                     and mapped.get("memory_commit", {}).get("status") == "committed")
        mapped["course_navigation"] = dict(navigation_row, explained=explained)
    return mapped


__all__ = ["run_agent_loop_turn"]
