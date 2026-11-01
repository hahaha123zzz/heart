"""Wire the Q3 local loop into the project's task identity and page result shape."""
from __future__ import annotations

from copy import deepcopy
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


def _target_from_context(context: TaskContext) -> LearningTarget:
    if context.input_mode == 'active' and context.activity_target:
        return LearningTarget(**context.activity_target, reason='有效待答任务绑定；阅读位置仅作背景')
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
        if re.search(r'<\s*/?\s*[｜|]+\s*DSML\s*[｜|]+|<tool_call(?:\s|>)', text, re.IGNORECASE):
            return False, '模型返回了内部工具协议，不能作为教学回答发布。'
        if not result.sources and (teaching is None or teaching.evidence_mode == "textbook"):
            return False, "本轮没有可核验的教材来源，暂不发布正式回答。"
        if not result.sources and re.search(r"\[\d+\]", text):
            return False, "本轮没有教材引用来源；请移除虚构的引用编号，并明确这是课堂补充知识。"
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
        from knowledge.fixed_book import active
        if active() and result.sources and not re.search(r'\[\s*\d', text):
            # 已有教材证据的改述不因缺少重复上标而撤回，也不自动编造引用。
            result._publication = {'reply':text,'pdf_references':[],'textbook_sources':[]}
            return True, ''
        if result.sources:
            format_issue = _citation_format_issues(text)
            if format_issue:
                return False, format_issue
            if not re.search(r"\[\d+\]", text):
                return False, "回答未标注本轮教材引用编号，暂不发布。"
        evidence = [source.get('location', {}).get('evidence') for source in result.sources]
        if any(evidence):
            if not all(evidence):
                return False, '本轮混入未经原文核验的来源，暂不发布。'
            try:
                from knowledge.grounded_citations import EvidenceBundle
                from knowledge.lightrag.retrieval import as_textbook_chunk
                bundle = EvidenceBundle([as_textbook_chunk(s) for s in result.sources], evidence, [])
                positions = {int(s.get('index') or i): i for i, s in enumerate(result.sources, 1)}
                if not {int(n) for n in re.findall(r'\[(\d+)\]', text)} <= positions.keys():
                    return False, '引用编号不属于本轮已核验来源。'
                grounded_text = re.sub(r'\[(\d+)\]', lambda m: f'[{positions[int(m[1])]}]', text)
                body, sources, references = bundle.publish(grounded_text)
                result._publication = {'reply': body, 'pdf_references': references,
                                       'textbook_sources': [f'{s.source} · {s.section}' for s in sources]}
            except ValueError as exc:
                return False, '本次原文发布核验失败：' + str(exc)
        excerpts = _excerpts(result.sources)
        if result.sources:
            issues = citation_issues(text, excerpts)
            if issues:
                return False, "本次引用未通过核验：" + "；".join(issues)
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
            "reply": result.final_text or "本次执行未完成，请重试或缩小问题范围。",
            "answer_status": result.error if result.error in {"answer_interrupted", "incomplete_answer", "active_timeout", "model_unavailable"} else "loop_failed",
            "unpublished_draft": result.unpublished_draft,
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
    from agents.tools.first_wave_runtime import purpose, bind_resources, STRUCTURED_TOOL, structured_gate, skill_catalog
    tool_purpose = 'textbook' if selection_input is not None else purpose(request.message)
    resources, first_tools = None, ()
    try:
        if selection_input is None:
            resources, first_tools = bind_resources(request, getattr(orchestrator, 'memory', None))
    except (OSError, ValueError, KeyError):
        # 未部署教材资源的隔离/旧课程环境不虚挂空工具。
        pass
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
        navigation.reader_location = request.reader_location
    decision: NavigationDecision = navigation.resolve(
        message=request.message, student_id=request.student_id,
        session_id=request.session_id, current_target=current_target,
        context=context,
    )
    if decision.action == "clarify" and decision.missing and tool_purpose == 'textbook':
        release(request.task_id or request.request_id)
        return {
            "reply": "需要先确定本轮学习目标：当前没有可用的课程路径或明确的下一目标，"
                     "因此不会用“下一知识点”原句直接检索教材。",
            "answer_status": "navigation_required",
            "step_advanced": False,
            "navigation": {"action": decision.action, "missing": list(decision.missing),
                           "reason": decision.reason},
        }
    target = decision.target or current_target or LearningTarget('course-context', context.knowledge_point or '教材')
    from agents.adaptive_tutoring import enabled as tutoring_enabled, TeachingTurn, TeachingStepTool
    if guard:
        guard()
    if resume_state and previous:
        context.tutoring = deepcopy((previous.get('context') or {}).get('tutoring') or context.tutoring)
    teaching = TeachingTurn(context, request, llm or orchestrator.llm, target=target, resume=bool(resume_state)) if tutoring_enabled() and tool_purpose == 'textbook' else None
    if (teaching and teaching.input_turn and teaching.input_turn.context.pending_question_id
            and teaching.sources_invalidated):
        release(request.task_id or request.request_id)
        return {'reply':'原待答题的教材来源已失效，不能恢复或评分。请重新选择教材内容后出题。',
                'answer_status':'reference_stale','step_advanced':False}
    initial_sources = teaching.sources if teaching else []
    resume_needs_evidence = bool(resume_state and not resume_state.get('sources') and tool_purpose == 'textbook')
    from knowledge.fixed_book import search_query
    prefetch_message = search_query(request.message) if resume_needs_evidence else request.message
    if selection_input is not None:
        initial_sources = initial_sources or selection_input.initial_sources()
        if teaching and ('no_questions' in selection_input.execution.answer_constraints
                         or selection_input.execution.hint_only):
            teaching.apply_strategy_constraints(selection_input.execution.answer_constraints)
    if guard:
        guard()
    from agents.course_search import explicit_chapters, question_interjection
    chapters = explicit_chapters(request.message)
    interjection = bool(len(chapters) > 1 or
        (q5_binding and question_interjection(request.message, target))
        or (teaching and teaching.interjection) or tool_purpose != 'textbook')
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
    # 输入层启用后，路径写入由宿主显式命令执行；模型不能从历史资料推导推进授权。
    host_owned_learning = context.input_mode == 'active'
    if interjection or host_owned_learning:
        q5_tools = tuple(tool for tool in q5_tools if tool.definition.name in ('mastery_status', 'mastery_paths'))
    registry = build_registry(
        workspace_root=workspace_root,
        skills_root=skills_root,
        allow_workspace=allow_workspace,
        allow_skills=skills_root.is_dir(),
        extra_tools=(*q5_tools, ContextualRetrieveCourseTool(), *first_tools,
                     *((TeachingStepTool(teaching),) if teaching else ())),
        extra_scopes=tuple({'learning:read'} if interjection or host_owned_learning else set((q5_binding or {}).get('scopes') or ())) +
                     tuple({scope for tool in first_tools for scope in tool.scopes}),
    )
    budget = reply_budget(request.message)
    system_prompt = build_loop_system_prompt(
        target=target, definitions=registry.definitions(),
        teaching_prompt=teaching.instructions() if teaching else "",
        verified_sources=initial_sources) + "\n" + budget.instructions()
    from agents.input_understanding.adapters import active_turn
    input_turn = active_turn(context)
    if input_turn:
        system_prompt += '\n' + input_turn.instructions()
    typed_queries = [t.query for t in input_turn.tasks if t.action in (
        'explain_content','compare_content','provide_hint','discuss_claim') and t.query] if input_turn else []
    typed_prefetch = bool(input_turn and input_turn.parser == 'model' and len(typed_queries) > 1
                          and input_turn.resolution_status in ('resolved', 'partial'))
    fallback_prefetch = bool(input_turn and input_turn.parser == 'fallback'
                             and 'complex_parse_unavailable' in input_turn.unresolved)
    if typed_prefetch:
        prefetch_message = '；'.join(typed_queries)[:4000]
    if tool_purpose == 'textbook':
        from agents.teaching_policy import resolve_teaching_mode, teaching_mode_instructions
        from models.interaction_preferences import style_instructions
        # 当前有效偏好在普通问答中也生效，不依赖Q5本次安排或辅助教学开关。
        system_prompt += '\n' + style_instructions(context.preferences)
        if teaching is None:
            system_prompt += '\n' + teaching_mode_instructions(resolve_teaching_mode(request.message))
    if selection_input is not None:
        system_prompt += '\n' + selection_input.instructions()
    required_tools = ()
    if resources:
        import json
        system_prompt += '\n授权教材文档（使用此处ID/版本和阅读版页码，不编造）：\n' + json.dumps(resources.course.files(resources.binding), ensure_ascii=False)
        system_prompt += skill_catalog(skills_root, resources.binding.course_id) if skills_root.is_dir() else ''
        if tool_purpose in STRUCTURED_TOOL:
            required_tools = (STRUCTURED_TOOL[tool_purpose],)
            system_prompt += '\n本轮只读取目录/盘点/画像或请求页面定位，不是教材知识讲解。先调用 ' + required_tools[0] + '，不添加教材事实或学习完成判断。'
        else:
            needed = []
            if re.search(r'偏好|我的基础|记得我', request.message) and resources.memory:
                needed.append('read_memory')
                system_prompt += '\n先读取当前偏好，再结合本轮教材原文回答；偏好缺失不推断。'
            if re.search(r'跳转|带我到|定位到', request.message):
                needed.append('reader_goto')
            if re.search(r'展开.{0,12}来源|补读|来源.{0,12}(完整|上下文)', request.message):
                needed.append('read_source')
            required_tools = tuple(needed)
    if not resume_state and re.search(r'(?:请先用|先用|请用)问题卡|先调用\s*ask_user', request.message):
        required_tools = tuple(dict.fromkeys((*required_tools, 'ask_user')))
        system_prompt += '\n用户明确要求先用问题卡：必须调用 ask_user 并暂停，不能用普通文字提问代替。'
    needs_review_evidence = bool(teaching and teaching.teaching_mode == 'review'
        and tool_purpose == 'textbook' and 'ask_user' not in required_tools)
    if needs_review_evidence and not initial_sources:
        system_prompt += '\n本轮回顾当前课程知识：先实际调用retrieve_course读取原文，再整理关系与重点依据；工具协议文本不能代替检索，不另行出题。'
    needs_teaching_question = bool(teaching and teaching.teaching_mode in ('guided', 'practice')
        and teaching.strategy_decision.invite_check and teaching.state['allow_check']
        and not teaching.progress.pending_question and not teaching.interjection
        and 'ask_user' not in required_tools)
    if needs_teaching_question:
        required_tools = tuple(dict.fromkeys((*required_tools, 'teaching_step')))
        system_prompt += '\n本轮明确要求引导或练习：必须用teaching_step登记一个check_prompt/check_focus，再把同一问题放在正文最后并停止。不能只在正文提问而不登记待答题。'
        if not initial_sources:
            system_prompt += '\n本轮尚无核验来源，先检索教材再登记与原文相符的检查；不能生成没有可核验依据的待答题。'
    needs_presentation = bool(teaching and not needs_teaching_question and 'ask_user' not in required_tools
            and re.search(r'分步展开|逐步展示|对比卡|比较卡', request.message))
    if needs_presentation:
        required_tools = tuple(dict.fromkeys((*required_tools, 'teaching_step')))
        system_prompt += '\n学生要求结构化回看：用teaching_step的card_kind生成step_reveal（explanation_steps）或concept_comparison（comparison_labels/comparison_rows）；source_indices只用本轮实际来源，正文由同一份数据生成并核验，无需再次改写。卡片不登记新检查题。'
    if interjection:
        system_prompt += '\n本轮是插问，只回答学生当前问题；保留原学习目标，不记录本目标已讲解、掌握或推进路径。'
    system_prompt += '\n页面当前学习目标仅作学习位置参考；具体提问优先，不要把旧小节主题擅自追加到检索词。指定图号先调用 retrieve_course 读取该图及登记原文，不能只检索旧主题便要求学生上传已有原图。'
    if q5_binding and q5_binding.get('session_study'):
        import json
        snapshot={k:v for k,v in q5_binding['session_plan'].items() if k not in ('student_id','session_id')}
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
        kind = event_type.removeprefix('loop-')
        labels = {'stage_start':'准备本轮处理', 'tool_call':'读取所需资料', 'tool_result':'资料读取完成',
                  'sources':'教材依据已就绪', 'wait_for_input':'等待补充信息', 'answer':'回答已核验',
                  'done':'本轮完成', 'error':'本轮未完成', 'progress':'处理中'}
        detail_text = {'retrieve_course':'读取教材原文', 'ask_user':'确认必要信息',
                       '探索':'准备取证或确认问题', 'sources':'已取得本轮教材原文'}.get(str(text), str(text))
        progress('loop-' + kind, labels.get(kind, '处理中'), detail_text[:300])

    round_tokens = max(1200, budget.max_tokens)
    tool_seconds = 120  # 共享活动预算还会取剩余时间的较小值。
    loop = LocalAgentLoop(llm or orchestrator.llm, max_round_tokens=round_tokens)
    cancellation = register(request.task_id or request.request_id)
    navigation.cancellation = cancellation
    if navigation.coverage is not None:
        navigation.coverage.cancellation = cancellation
    if navigation.backend is not None and hasattr(navigation.backend, 'cancellation'):
        navigation.backend.cancellation = cancellation
    base_gate = publish_gate or (structured_gate(tool_purpose) if resources and tool_purpose in STRUCTURED_TOOL
                                 else _publish_gate(orchestrator, request, target, navigation, teaching, selection_input))

    def final_gate(text, outcome):
        if (teaching and not teaching.state['allow_check'] and re.search(r'[？?]',text)
                and not (teaching.input_turn and teaching.input_turn.only_resume_question)):
            return False, '学生要求先讲不考：请将疑问句改为陈述句并自然收束。'
        missing = set(required_tools) - {row.get('tool') for row in outcome.tool_outputs}
        if missing:
            return False, '所需读取或页面请求尚未成功：' + '、'.join(sorted(missing))
        if needs_presentation:
            from agents.learning_cards import build_learning_cards, presentation_text
            if not teaching.state.get('presentation'):
                return False, '教学卡片未正确呈现：请用teaching_step登记所要求的卡片内容。'
            text = presentation_text(teaching.state['presentation'])
            if not any(card['kind'] != 'learning_progress' for card in build_learning_cards(teaching, outcome.sources, text)):
                return False, '教学卡片未正确呈现：卡片内容必须也出现在完整正文，引用编号须已在正文使用；请修正卡片后再回答。'
        if needs_teaching_question and not teaching.progress.pending_question:
            return False, '教学检查未正确呈现：请用teaching_step登记一个待答步骤，再将问题放在正文最后。'
        if needs_teaching_question and not outcome.sources:
            return False, '本轮没有可核验的教材来源，暂不发布正式回答。'
        if teaching and (teaching.new_question or teaching.show_pending):
            accepted, reason = teaching.gate(text)
            if not accepted:
                return False, reason
        accepted, reason = base_gate(text, outcome)
        if accepted and needs_presentation:
            publication = getattr(outcome, '_publication', None) or {}
            publication.setdefault('reply', text)
            outcome._publication = publication
        return accepted, reason

    restored_reply = teaching.restore_reply() if teaching and not required_tools else None
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
                round_max_tokens=round_tokens, requires_evidence=(tool_purpose == 'textbook' and
                    (resume_needs_evidence or needs_teaching_question or needs_review_evidence or teaching is None or teaching.evidence_mode != 'blended')),
                required_tools=required_tools,
                bound_media_id=next((r.canonical_id for r in input_turn.references
                    if r.kind == 'figure' and r.status == 'resolved' and r.origin == 'history'
                    and any(t.target_ref == r.ref_id for t in input_turn.tasks)),None) if input_turn else None,
                structured_response=bool(needs_presentation or resources and tool_purpose in STRUCTURED_TOOL and publish_gate is None),
                answer_ready=((lambda outcome: bool(outcome.sources) or
                    (teaching.evidence_mode == 'blended' and not resume_needs_evidence
                     and not needs_teaching_question and not needs_review_evidence)) if teaching else None),
                prefetch_query=(prefetch_message if resume_needs_evidence or (tool_purpose == 'textbook' and 'ask_user' not in required_tools and not resume_state and not initial_sources and (
                    typed_prefetch or fallback_prefetch or q5_binding or (context.course_navigation or {}).get("status")=="ready" or
                    (getattr(navigation.backend,"backend",None) is not None and target is not None and
                     (question_interjection(request.message,target) or target.name in request.message)))) else None),
                seed_messages=([] if selection_input and selection_input.scope_changed
                               else list(context.history or [])), target=target,
                initial_sources=initial_sources,
                navigation=navigation, cancellation=cancellation, guard=guard,
                tool_state={"workspace_root": str(workspace_root),
                            "skills_root": str(skills_root), "deferred_loader": None,
                            'allowed_skills': ('reasoning-diagrams', 'experimental-design') if resources and resources.binding.course_id == 'experimental-psychology-3' else ('reasoning-diagrams', 'finite-structures'),
                            **({'first_wave': resources} if resources else {}),
                            **((q5_binding or {}).get("tool_state") or {})},
                publish_gate=final_gate,
                evidence_repair=teaching.repair_evidence if teaching else None,
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
    if teaching and result.error and teaching.plan.evidence_recovery == 'attempted':
        teaching.plan.evidence_recovery = 'blocked'
        teaching._sync()
    if teaching and result.completed:
        teaching.commit_sources(result.sources, answer_text=result.final_text, tool_outputs=result.tool_outputs)
        mapped["teaching"] = teaching.public()
    if teaching and mapped.get("loop_state"):
        from agents.adaptive_tutoring import redact_protocol
        mapped["loop_state"] = redact_protocol(mapped["loop_state"])
    if selection_input is not None:
        mapped['entrypoint'] = 'pdf_text_selection'
        mapped['selection_ref'] = selection_input.reference
        mapped['pdf_image_refs'] = selection_input.reference.get('image_refs', [])
    if result.completed:
        actions = [row['data']['action'] for row in result.tool_outputs if row.get('result_kind') == 'reader_action']
        mapped['reader_actions'] = actions[-1:]
    if result.completed:
        media = {}
        for source in result.sources:
            for image in source.get('image_refs', []):
                media[image['id']] = image
        mapped['image_refs'] = list(media.values())[:2]
    if result.completed and getattr(result, '_publication', None):
        mapped.update(result._publication)
    if (input_turn and input_turn.explain_then_resume and teaching and result.completed
            and teaching.progress.pending_question):
        question = teaching.progress.pending_question.prompt
        suffix = '\n\n回到原来的题（尚未提交答案）：\n\n' + question
        if not mapped['reply'].rstrip().endswith(question.rstrip()):
            mapped['reply'] += suffix
            from llm.answer_events import current_answer
            answer = current_answer.get()
            if answer:
                answer.delta(suffix)
        mapped['input_resume_question_id'] = teaching.progress.pending_question.question_id
    if teaching and result.completed:
        from agents.learning_cards import build_learning_cards, published_reference_map
        reference_map = published_reference_map(result.sources, mapped['pdf_references'])
        mapped['learning_cards'] = build_learning_cards(teaching, result.sources, result.final_text,
                                                      reference_map=reference_map)
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
                for card in mapped.get('learning_cards', []):
                    card['memory_epoch'] = epoch
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
                if mapped.get('learning_cards'):
                    stored_reference['learning_cards'] = mapped['learning_cards']
                conversation_id = memory.append_exchange(
                    request.student_id, user_message, result.final_text,
                    selection_ref=stored_reference
                    if stored_reference["pdf_references"] or stored_reference["textbook_sources"] or stored_reference.get('learning_cards')
                    else None,
                    expected_epoch=epoch, expected_point=target.name, task_guard=guard,
                    session_id=request.session_id)
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
