"""可恢复的澄清控制层；模型与执行通过回调，写事务不覆盖模型调用。"""
import inspect
import re
from uuid import uuid4
from database.learning_tasks import LearningTaskRepository, TaskConflict
from models.chat_request import ChatRequest
from agents.task_context_builder import TaskContextBuilder
from knowledge.pdf_reader import resolve_selection
from knowledge.course import get_section
from knowledge.course_config import DEFAULT_GOAL
from agents.intent_policy import IntentPolicy
from visualization.service import VisualizationError


class TaskService:
    def __init__(self, tutor, repository=None, *, ttl_seconds=1800, max_clarifications=2, policy=None):
        self.tutor = tutor
        self.repo = repository or LearningTaskRepository()
        if ttl_seconds < 1 or max_clarifications < 1: raise ValueError("任务有效期和澄清次数必须为正数")
        self.ttl_seconds = ttl_seconds
        self.max_clarifications = max_clarifications
        self.policy = policy if policy is not None else IntentPolicy.from_env()

    def conflict_reply(self, error):
        return {"reply": str(error), "answer_status": error.code, "step_advanced": False}

    @staticmethod
    def _accepts_previous(executor):
        try:
            return "previous" in inspect.signature(executor).parameters
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _selected_label(request, previous):
        """Return the clickable label for an ask_user answer, else raw text."""
        clarification = (previous or {}).get("result", {}).get("clarification") or {}
        options = clarification.get("options") or []
        chosen = request.selected_option
        if chosen is None:
            match = re.fullmatch(r"第?([一二三四1234])个[。！!]?", request.message.strip())
            if match:
                position = {"一": 0, "二": 1, "三": 2, "四": 3,
                            "1": 0, "2": 1, "3": 2, "4": 3}[match[1]]
                if position < len(options):
                    chosen = options[position].get("id")
        for option in options:
            if chosen is not None and option.get("id") == chosen:
                return str(option.get("label") or request.message)
        return request.message

    @staticmethod
    def _last_navigation_cursor(recent):
        """Find the newest valid Q2 cursor when a later turn did not persist one.

        A non-navigation follow-up can be answered without a directory cursor;
        the next "下一部分" must still continue from the last valid path.
        """
        for row in reversed(recent or ()):
            result = row.get("result") or {}
            if result.get("answer_status") != "answered":
                continue
            navigation = result.get("course_navigation")
            if isinstance(navigation, dict) and navigation.get("status") == "ready":
                return navigation
        return None

    @staticmethod
    def _prefer_current_cursor(bound, previous):
        """Keep the established path when a cross-section answer is ambiguous.

        Q2's ``bind_result`` correctly returns ``clarify`` when one answer cites
        several sections.  That must not erase a cursor the student was already
        following; otherwise the next "下一部分" becomes a dead end.
        """
        if isinstance(bound, dict) and bound.get("status") == "ready":
            return bound
        if isinstance(previous, dict) and previous.get("status") == "ready":
            return dict(previous, explained=True)
        return bound

    @staticmethod
    def _needs_navigation_fallback(message):
        """Whether Q2 should resume from the last valid cursor on this turn."""
        return bool(re.search(
            r"(?:我懂了|明白了|懂了|学会了|清楚了).{0,8}(?:下一部分|下一段|继续往下|往下学)|"
            r"(?:下一部分|下一段)|(?:继续|接着)(?:下一个?知识点|下一部分|往下)", message.strip()))

    def _context(self, request):
        recent = self.repo.recent(request.student_id, request.session_id, limit=12)
        history = self.tutor.memory.get_history(request.student_id) if request.session_id == "legacy" else [
            item for row in recent for item in ({"role": "user", "content": row["payload"].get("message", "")},
                {"role": "assistant", "content": row["result"].get("reply", "")})]
        point = request.learning_goal or (recent[-1]["knowledge_point"] if recent else None) or self.tutor.memory.get_active_goal(request.student_id) or DEFAULT_GOAL
        resolved = resolve_selection(request.selection) if request.selection else None
        if resolved: point = resolved["section"]["title"]
        elif request.reader_location:
            section = get_section(request.reader_location.chapter_id, request.reader_location.section_id)
            if not section: raise ValueError("教材小节不存在")
            point = section["title"]
        if request.exercise_target:
            from practice_api import catalog
            point = catalog()["by_id"][request.exercise_target.question_id]["knowledge_point"]
        if request.visualization_target:
            from visualization.service import POINT
            point = POINT
        if request.truth_table_target:
            from visualization.truth_table import POINT
            point = POINT
        if request.relation_target:
            from visualization.relation import POINT,CLOSURE_POINT
            point=CLOSURE_POINT if request.relation_target.closure else POINT
        builder = TaskContextBuilder()
        context = builder.build(student_id=request.student_id, message=request.message, knowledge_point=point,
            history=history, known_points=self.tutor.memory.list_knowledge_points(request.student_id),
            reader_location=request.reader_location, selection=request.selection, exercise_target=request.exercise_target,
            resolved_selection=resolved, session_id=request.session_id, request_id=request.request_id,
            visualization_target=request.visualization_target,
            truth_table_target=request.truth_table_target,
            relation_target=request.relation_target,
            preferences={**self.tutor.memory.get_profile(request.student_id).preferences,
                **(request.style_overrides.model_dump(exclude_none=True) if request.style_overrides else {})})
        from knowledge.course_navigation import resolve, previous_cursor
        cursor = previous_cursor(recent, self.tutor.memory, request.student_id)
        if cursor is None and self._needs_navigation_fallback(request.message):
            cursor = self._last_navigation_cursor(recent)
        if not any((request.selection, request.exercise_target, request.visualization_target,
                    request.truth_table_target, request.relation_target)):
            context.course_navigation = resolve(request.message,
                                                cursor=cursor, reader_location=request.reader_location)
            if (context.course_navigation is None and cursor and re.fullmatch(
                    r'(?:我|还是|刚才|请|没听懂|再解释(?:一次|一下|一遍)?|换(?:个|一种)说法|'
                    r'再简单(?:点|一点)?|继续这个例子|继续讲|接着讲|[，。！？、\s])+', request.message)):
                context.course_navigation = dict(cursor, mode='repeat', explained=False)
            if context.course_navigation and context.course_navigation['status'] == 'ready':
                context.knowledge_point = context.course_navigation['title']
        def origin(source, obj):
            values = {"reader_location": None, "selection": None, "exercise_target": None, "visualization_target": None, "truth_table_target": None, "relation_target":None}
            key = {"section": "reader_location", "pdf_selection": "selection", "exercise_part": "exercise_target", "visualization":"visualization_target", "truth_table":"truth_table_target", "relation":"relation_target"}[obj.kind]
            values[key] = source.model_dump()[key]
            if key in ('visualization_target', 'truth_table_target', 'relation_target'):
                values[key] = dict(values[key], action=None)
            return values
        origins = {obj.id: origin(request, obj) for obj in context.objects}
        # 指代候选只来自该会话已完成的任务，并重新验证资源版本。
        for row in reversed(recent):
            try:
                old = ChatRequest.model_validate(row["payload"])
                previous = builder.build(student_id=request.student_id, message=old.message,
                    reader_location=old.reader_location, selection=old.selection, exercise_target=old.exercise_target,
                    session_id=request.session_id, visualization_target=old.visualization_target,
                    truth_table_target=old.truth_table_target,
                    relation_target=old.relation_target,
                    mark_graph_assisted=False)
            except (ValueError, VisualizationError):
                continue
            for obj in previous.objects:
                if obj.id not in origins and len(context.objects) < 4:
                    context.objects.append(obj)
                    origins[obj.id] = origin(old, obj)
        from agents.adaptive_tutoring import enabled as tutoring_enabled, snapshot_from_recent
        if tutoring_enabled():
            context.tutoring = snapshot_from_recent(
                recent, context, self.tutor.memory.repo, request.student_id)
        return context, resolved, origins

    def _resume(self, request, row):
        payload = dict(row["payload"])
        options = row["result"].get("clarification", {}).get("options", [])
        chosen = request.selected_option
        if chosen is None:
            match = re.fullmatch(r"第?([一二三四1234])个[。！!]?", request.message.strip())
            if match:
                position = {"一": 0, "二": 1, "三": 2, "四": 3, "1": 0, "2": 1, "3": 2, "4": 3}[match[1]]
                if position >= len(options): raise TaskConflict("invalid_option", "没有这个选项，请选择列出的对象")
                chosen = options[position]["id"]
        suffix = "\n补充说明：" + request.message
        if chosen:
            option = next((value for value in options if value["id"] == chosen), None)
            if option is None:
                raise TaskConflict("invalid_option", "选项不存在或已失效，请恢复最新任务")
            clarification_mode = row["result"].get("clarification", {}).get("mode")
            if clarification_mode == "ask_user":
                suffix += "\n明确回答：" + option["label"]
            elif clarification_mode in ("q5_plan", "q5_plan_adjust", "q5_session_plan", "q5_session_adjust", "q5_session_intake"):
                suffix += "\n明确选择：" + option["label"]
            else:
                origin = row["context"].get("option_requests", {}).get(chosen)
                if origin is None:
                    raise TaskConflict("invalid_option", "选项不存在或已失效，请恢复最新任务")
                payload.update(origin)
                suffix += "\n明确对象：" + option["label"]
        elif "不是这个" in request.message:
            payload.update(selection=None, exercise_target=None, reader_location=None, visualization_target=None, truth_table_target=None,relation_target=None)
        # 若用户重新圈选或明确新题，则以补充请求的已校验资源覆盖旧对象。
        for field in ("selection", "exercise_target", "reader_location", "visualization_target", "truth_table_target", "relation_target"):
            if getattr(request, field) is not None:
                payload[field] = request.model_dump()[field]
        merged = payload["message"] + suffix
        if len(merged) > 4000: raise TaskConflict("task_too_long", "补充后的问题过长，请重新提问")
        payload.update(message=merged, request_id=request.request_id, task_id=None, task_revision=None, selected_option=None,
            style_overrides=request.model_dump()["style_overrides"])
        return ChatRequest.model_validate(payload)

    def run(self, request, executor, progress=None, *, visualization_jobs=None, answer_ready=None, answer_event=None):
        from llm.answer_events import AnswerEvents, current_answer
        answer = AnswerEvents(answer_event) if answer_event else None
        token = current_answer.set(answer)
        try:
            result = self._run(request, executor, progress, visualization_jobs=visualization_jobs, answer_ready=answer_ready)
            if answer and answer.identity:
                # 已保存任务的 guard 只允许执行态；用既有收据复核最终版本及 epoch。
                try:
                    replay = self.repo.replay(request.student_id, request.session_id, request.request_id,
                                              request.model_dump(), self.tutor.memory.repo)
                    if replay and replay.get('task_id') == result.get('task_id') and replay.get('task_revision') == result.get('task_revision'):
                        answer.finish(result)
                except TaskConflict:
                    pass
            return result
        finally:
            current_answer.reset(token)

    def _run(self, request, executor, progress=None, *, visualization_jobs=None, answer_ready=None):
        try:
            # 模型未开始前确保账户；后续执行器在task_guard存在时不重建账户。
            if request.account_type == "test": self.tutor.memory.accounts.create_test_account(request.student_id, ttl_hours=24)
            elif request.account_type == "production": self.tutor.memory.ensure_student(request.student_id, account_type="production")
            else: raise ValueError("账户类型无效")
            # 灰度使用数据库中的账户类别，客户端不能把正式账户伪装成测试账户。
            account_type = self.repo.account_type(request.student_id)
            q5 = None
            from agents.q5_runtime import q5_enabled, Q5Runtime
            if q5_enabled():
                q5 = Q5Runtime(request.student_id, request.session_id)
            enabled = self.policy.enabled(request.student_id, account_type)
            can_clarify = self.policy.can_clarify(request.student_id, account_type)
            if not can_clarify:
                invalidated = self.repo.invalidate_pending(request.student_id, request.session_id)
                if request.task_id:
                    self.repo.get(request.student_id, request.session_id, request.task_id)
                old_slot_reply = self.repo.rolled_back(request.student_id, request.session_id) and re.fullmatch(
                    r"第?[一二三四1234]个[。！!]?", request.message.strip())
                if request.task_id or invalidated or old_slot_reply:
                    return {"reply": "任务模式已关闭，上一个待补充问题已失效，请完整重新提问。",
                        "answer_status": "task_disabled", "step_advanced": False}
            payload = request.model_dump()
            request_key = request.request_id or str(uuid4())
            self.repo.expire(request.student_id, request.session_id)
            replay = self.repo.replay(request.student_id, request.session_id, request_key, payload, self.tutor.memory.repo)
            if replay is not None:
                from knowledge.grounded_citations import references_for_display
                return dict(replay,pdf_references=references_for_display(replay['pdf_references'])) if replay.get('pdf_references') else replay
            pending = self.repo.pending(request.student_id, request.session_id)
            task_id, revision = request.task_id, request.task_revision
            if task_id is None and pending and not re.search(r"换到|换个|改学|想学|重新提问", request.message):
                task_id, revision = pending["id"], pending["revision"]
            previous = self.repo.resume(request.student_id, request.session_id, task_id, revision, self.tutor.memory.repo) if task_id else None
            if previous is not None:
                # The loop needs the raw answer, not the merged "补充说明" body.
                previous["_resume_answer"] = self._selected_label(request, previous)
            effective = self._resume(request, previous) if previous else request
            previous_result = (previous or {}).get("result") or {}
            q5_plan = previous_result.get("q5_plan") if isinstance(previous_result, dict) else None
            q5_previous_mode = (previous_result.get("clarification") or {}).get("mode")
            q5_propose = bool(q5 and q5.is_plan_request(request.message))
            session_draft = previous_result.get('q5_session_plan')
            if q5 and not session_draft and q5.is_adjust(request.message):
                session_draft = q5.sessions.current()
            session_confirm = bool(q5 and session_draft and q5_previous_mode in ('q5_session_plan','q5_session_adjust')
                and (request.selected_option=='q5sp:confirm' or q5.is_confirm(request.message)))
            session_adjust_prompt = bool(q5 and session_draft and request.selected_option=='q5sp:adjust')
            session_revise = bool(q5 and session_draft and q5.is_adjust(request.message) and not session_adjust_prompt)
            session_intake = bool(q5 and session_draft and q5_previous_mode=='q5_session_intake')
            q5_adjust_prompt = bool(
                q5 and q5_plan and request.selected_option == "q5:adjust"
            )
            q5_adjust_text = bool(
                q5 and q5_plan and q5_previous_mode == "q5_plan_adjust"
                and request.selected_option is None and q5.is_adjust(request.message)
            )
            q5_confirm = bool(
                q5 and q5_plan
                and (request.selected_option == "q5:confirm" or q5.is_confirm(effective.message))
                and q5_previous_mode in ("q5_plan", "q5_plan_adjust")
            )
            context, resolved, origins = self._context(effective)
            from knowledge.pdf_reader import documents
            document_versions = {record["document_id"]: record["version"] for record in documents()}
            context.task_understanding_enabled = enabled
            if not self.policy.context or not enabled:
                if effective.visualization_target or effective.truth_table_target or effective.relation_target:
                    raise TaskConflict('task_disabled', '互动图提问需要开启任务上下文，本轮没有推进学习进度')
                context.objects = []
            point = context.knowledge_point
            epoch = self.tutor.memory.repo.memory_epoch(request.student_id, point)
            task, receipt, duplicate = self.repo.claim(student_id=request.student_id, session_id=request.session_id,
                request_id=request_key, payload=payload, point=point, epoch=epoch, memory_repo=self.tutor.memory.repo,
                task_id=task_id, revision=revision, ttl_seconds=self.ttl_seconds)
            if duplicate is not None:
                from knowledge.grounded_citations import references_for_display
                return dict(duplicate,pdf_references=references_for_display(duplicate['pdf_references'])) if duplicate.get('pdf_references') else duplicate

            q5_binding = None
            if q5 is not None:
                def save_q5(result):
                    saved_context = context.model_dump() | {
                        "document_versions": document_versions,
                        "q5_status": result.get("q5_status"),
                    }
                    saved_task, saved_result = self.repo.save(
                        task=task, receipt_id=receipt,
                        memory_repo=self.tutor.memory.repo,
                        status="awaiting_clarification" if result.get("loop_paused") else "completed",
                        result=result, context=saved_context, routing=None,
                        payload=effective.model_dump(),
                    )
                    return saved_result

                try:
                    def planning_guard():
                        self.repo.guard(task['student_id'],task['session_id'],task['id'],task['revision'],self.tutor.memory.repo)
                    if session_confirm:
                        q5.sessions.confirm(session_draft,command_id=request_key+':session-confirm',guard=planning_guard)
                    elif session_adjust_prompt:
                        return save_q5(q5.session_result(session_draft,task,adjust_prompt=True))
                    elif q5_propose or session_revise or session_intake:
                        if progress:progress('session_plan','安排本次学习','读取教材、核对画像与时间预算')
                        proposal = q5.propose_session(effective.message,self.tutor.llm,self.tutor.memory,
                            previous=session_draft if session_revise or session_intake else None,guard=planning_guard)
                        planning_guard()
                        return save_q5(q5.session_result(proposal,task))
                    if q5_adjust_prompt:
                        return save_q5(q5.plan_result(
                            q5_plan, task, adjust_prompt=True))
                    if q5_adjust_text:
                        proposal = q5.adjust_first(
                            q5_plan, request.message, request_key)
                        return save_q5(q5.plan_result(proposal, task))
                    if q5_confirm:
                        q5.confirm(q5_plan, request_key)
                    current_session = q5.sessions.current()
                    if current_session and current_session['status'] in ('active','paused'):
                        if re.fullmatch(r'(?:请)?暂停(?:本次安排|学习|一下)?[。！!\s]*',request.message):
                            plan=q5.sessions.set_mode(current_session,'paused',command_id=request_key+':pause',guard=planning_guard)
                            return save_q5({'reply':'本次安排已暂停，活动与长期路径均未推进。','answer_status':'answered',
                                'session_plan':plan,'result_type':'session_plan','step_advanced':False})
                        resumed=False
                        if current_session['status']=='paused' and re.fullmatch(r'(?:继续|恢复)(?:本次安排|学习)?[。！!\s]*',request.message):
                            q5.sessions.set_mode(current_session,'active',command_id=request_key+':resume',guard=planning_guard)
                            resumed=True
                        textbook_next=bool(re.search(r'教材.{0,6}下一|下一知识点',request.message))
                        execution=None if textbook_next else q5.prepare_session('' if resumed else request.message,context.preferences)
                        if execution and execution['status']=='done':
                            plan=q5.sessions.finish(execution,command_id=request_key+':finish',guard=planning_guard)
                            return save_q5({'reply':'本次安排已结束。已讲活动：'+ '、'.join(i['title'] for i in plan['items'] if i['status']=='done')+
                                '。未纳入内容：'+('；'.join(plan['omitted']) or '无额外安排')+'。活动完成不代表长期路径完成或已经掌握。',
                                'answer_status':'answered','session_plan':plan,'result_type':'session_plan','step_advanced':False})
                        if execution and execution['status']=='active':
                            q5_binding=q5
                            context.session_study_plan=execution
                            context.course_navigation=None
                    from agents.course_search import explicit_chapters
                    if not current_session and q5.is_understood(effective.message) and len(explicit_chapters(effective.message)) < 2:
                        q5.advance_understood(request_key)
                    status = q5.status()
                    if (q5_binding is None and not current_session and status.get("path_id") and status.get("plan_confirmed")
                            and status.get("mode") == "study"
                            and status.get("current")):
                        q5_binding = q5
                except (ValueError, RuntimeError) as exc:
                    result = {
                        "reply": f"学习计划暂时无法推进：{exc}",
                        "answer_status": "q5_error",
                        "step_advanced": False,
                        "task_id": task.get("id"), "task_revision": task.get("revision"),
                    }
                    return save_q5(result)
            def guard():
                self.repo.guard(task["student_id"], task["session_id"], task["id"], task["revision"], self.tutor.memory.repo)
                if q5 and q5.session_snapshot:
                    try:q5.session_guard()
                    except ValueError as exc:raise TaskConflict('session_plan_changed',str(exc)) from exc
                if context.course_navigation and context.course_navigation['status'] == 'ready':
                    from knowledge.course_navigation import validate
                    try:
                        validate(context.course_navigation)
                    except (ValueError, OSError) as exc:
                        raise TaskConflict('document_changed', str(exc)) from exc
                if context.relation_snapshot:
                    from visualization.relation import RelationService
                    try:RelationService().guard_snapshot(context.relation_snapshot,request.student_id,request.session_id)
                    except VisualizationError as exc:raise TaskConflict('visualization_changed',str(exc)) from exc
                if context.truth_table_snapshot:
                    from visualization.truth_table import TruthTableService
                    try:
                        TruthTableService().guard_snapshot(context.truth_table_snapshot, request.student_id, request.session_id)
                    except VisualizationError as exc:
                        raise TaskConflict('visualization_changed', str(exc)) from exc
                if context.graph_snapshot:
                    from visualization.service import VisualizationService
                    try:
                        VisualizationService().guard_snapshot(context.graph_snapshot, request.student_id, request.session_id)
                    except VisualizationError as exc:
                        raise TaskConflict('visualization_changed', str(exc)) from exc
            def intercept(routing, ignored=None):
                nonlocal task
                guard()
                if routing.status in ("parse_error", "unavailable"):
                    result = {"reply": "本次问题识别未完成，请重试。本次没有推进学习进度。", "answer_status": "routing_failed", "routing": routing.model_dump(), "step_advanced": False}
                    task, result = self.repo.save(task=task, receipt_id=receipt, memory_repo=self.tutor.memory.repo, status="failed", result=result)
                    return result
                needs = routing.status == "unknown" or routing.intent == "clarify_task"
                if needs:
                    if not can_clarify:
                        result = {"reply": "请完整说明问题和具体对象后重新提问；当前未启用多轮澄清。",
                            "answer_status": "clarification_required", "routing": routing.model_dump(), "step_advanced": False}
                        task, result = self.repo.save(task=task, receipt_id=receipt,
                            memory_repo=self.tutor.memory.repo, status="failed", result=result)
                        return result
                    slots = getattr(routing, "missing_slots", []) or ["topic"]
                    question = ("你指的是哪个对象？请选择或重新圈选教材内容。" if "target" in slots else
                        "你想继续哪个任务？" if "task" in slots else "你希望我解释、给提示还是展开证明？" if "answer_format" in slots else "你想学哪个具体知识点？")
                    options = [{"id": obj.id, "label": ('辅助图 '+str(index+1)+' · ' if obj.kind == 'visualization' else '')+obj.title}
                               for index,obj in enumerate(context.objects)] if "target" in slots else []
                    limited = task["clarification_count"] >= self.max_clarifications
                    result = {"reply": question if not limited else "仍缺少必要信息，请选中具体教材内容后重新提问。",
                        "answer_status": "awaiting_clarification" if not limited else "clarification_limit",
                        "routing": routing.model_dump(), "step_advanced": False,
                        "clarification": {"question": question, "options": options, "missing_slots": slots}}
                    saved_context = context.model_dump() | {"option_requests": origins, "document_versions": document_versions}
                    task, result = self.repo.save(task=task, receipt_id=receipt, memory_repo=self.tutor.memory.repo, status="failed" if limited else "awaiting_clarification",
                        result=result, context=saved_context, routing=routing.model_dump(), payload=effective.model_dump())
                    return result
                if context.graph_snapshot is None:
                    selected = [obj for obj in context.objects if obj.kind == 'visualization' and obj.id in routing.target_refs]
                    if len(selected) == 1:
                        from visualization.service import VisualizationService
                        from models.visualization import VisualizationTarget
                        target = VisualizationTarget.model_validate(origins[selected[0].id]['visualization_target'])
                        context.graph_snapshot = VisualizationService().snapshot(target, request.student_id, request.session_id)
                        guard()
                if context.truth_table_snapshot is None:
                    selected = [obj for obj in context.objects if obj.kind == 'truth_table' and obj.id in routing.target_refs]
                    if len(selected) == 1:
                        from visualization.truth_table import TruthTableService
                        from models.truth_table import TruthTableTarget
                        target = TruthTableTarget.model_validate(origins[selected[0].id]['truth_table_target'])
                        context.truth_table_snapshot = TruthTableService().snapshot(target, request.student_id, request.session_id)
                        guard()
                if context.relation_snapshot is None:
                    selected=[obj for obj in context.objects if obj.kind=='relation' and obj.id in routing.target_refs]
                    if len(selected)==1:
                        from visualization.relation import RelationService
                        from models.relation import RelationTarget
                        target=RelationTarget.model_validate(origins[selected[0].id]['relation_target'])
                        context.relation_snapshot=RelationService().snapshot(target,request.student_id,request.session_id)
                        guard()
                task, _ = self.repo.save(task=task, receipt_id=receipt, memory_repo=self.tutor.memory.repo, status="executing", result={},
                    context=context.model_dump() | {"document_versions": document_versions}, routing=routing.model_dump(), payload=effective.model_dump())
                return None
            guard()
            from llm.answer_events import current_answer
            answer = current_answer.get()
            if answer:
                # 每个增量检查取消/版本号；教材全量哈希仍在模型轮开始、核验和保存边界检查。
                answer.bind(lambda: {'task_id': task['id'], 'task_revision': task['revision']}, guard,
                            lambda: self.repo.guard(task['student_id'], task['session_id'],
                                task['id'], task['revision'], self.tutor.memory.repo))
            # 新任务也必须把已认领身份传给循环，使HTTP取消命中同一令牌。
            execution_request = effective.model_copy(update={
                'task_id': task['id'], 'task_revision': task['revision']})
            if q5_binding is not None:
                result = executor(execution_request, context, resolved, intercept, guard,
                                  progress, previous=previous,
                                  q5_binding=q5_binding)
            elif self._accepts_previous(executor):
                result = executor(execution_request, context, resolved, intercept, guard, progress, previous=previous)
            else:
                result = executor(execution_request, context, resolved, intercept, guard, progress)
            if result.get("loop_paused"):
                # ask_user pauses the same task; persist the pending question and
                # the complete loop protocol before returning to the page.
                guard()
                saved_context = context.model_dump() | {
                    "loop_state": result.get("loop_state"),
                    "document_versions": document_versions,
                }
                task, result = self.repo.save(
                    task=task, receipt_id=receipt, memory_repo=self.tutor.memory.repo,
                    status="awaiting_clarification", result=result, context=saved_context,
                    routing=result.get("routing"), payload=effective.model_dump(),
                )
                return result
            if (q5 is not None and q5_binding is not None
                    and not result.get('learning_interjection')
                    and result.get("answer_status") == "answered"):
                try:
                    q5.record_explained(str(result.get("reply") or ""), request_key,guard=guard)
                    result = dict(result, q5_status=q5.status())
                except (ValueError, RuntimeError):
                    pass
            if context.graph_snapshot:
                result['visualization_context'] = {k:v for k,v in context.graph_snapshot.items() if k != 'evaluation'}
            if context.truth_table_snapshot:
                result['truth_table_context'] = {k:v for k,v in context.truth_table_snapshot.items() if k != 'evaluation'}
            if context.relation_snapshot:
                result['relation_context']={k:v for k,v in context.relation_snapshot.items() if k!='evaluation'}
            if task["status"] in ("awaiting_clarification", "failed"): return result
            from agents.style_suggestions import suggest_style
            suggestion = suggest_style(result, context, self.repo.recent(request.student_id, request.session_id))
            if suggestion:
                result = dict(result, style_suggestion=suggestion)
            if visualization_jobs and result.get("answer_status") == "answered" and result.get("conversation_id"):
                guard()
                result = dict(result, visualization_status="pending")
                if answer_ready is not None:
                    answer_ready(dict(result))
                guide = None
                if progress:
                    progress("visualization", "准备辅助图解", "文字已保存，可先阅读回答")
                try:
                    for build in visualization_jobs:
                        guard()
                        guide = build()
                except TaskConflict:
                    raise
                except Exception:
                    # 图解是可选附件，失败不能抹掉已经保存的合格文字。
                    import logging
                    logging.getLogger(__name__).exception("Optional visualization failed")
                result = dict(result, guided_visualization=guide,
                    visualization_status="ready" if guide else "unavailable")
            # 普通问答/选区回答若引用真实教材位置，绑定可接续的目录游标；
            # 绑定只读文件，放在写事务之外，避免持锁做目录解析。
            bound_navigation = None
            if (result.get('answer_status') == 'answered'
                    and result.get('memory_commit', {}).get('status') == 'committed'
                    and context.course_navigation is None and not result.get('learning_interjection')):
                from knowledge.course_navigation import bind_result
                bound_navigation = bind_result(result)
                if bound_navigation and bound_navigation.get('status') != 'ready':
                    bound_navigation = self._prefer_current_cursor(
                        bound_navigation,
                        self._last_navigation_cursor(
                            self.repo.recent(request.student_id, request.session_id, limit=12)))
            # 与最后一次保存使用相同工作单元检查，拒绝已删除/取消的迟到结果。
            with self.tutor.memory.repo.unit_of_work():
                guard()
                if (result.get('answer_status') == 'answered' and result.get('memory_commit', {}).get('status') == 'committed'):
                    navigation = context.course_navigation
                    if navigation and navigation.get('status') == 'ready' and result.get('knowledge_point') == navigation['title']:
                        result = dict(result, course_navigation=dict(navigation, explained=True))
                    elif navigation is None and bound_navigation:
                        result = dict(result, course_navigation=bound_navigation)
                    elif navigation is None:
                        from knowledge.course_navigation import previous_cursor
                        navigation = previous_cursor(self.repo.recent(request.student_id, request.session_id, limit=12),
                                                     self.tutor.memory, request.student_id)
                        if navigation and navigation.get('status') == 'ready' and result.get('knowledge_point') == navigation['title']:
                            result = dict(result, course_navigation=dict(navigation, explained=True))
                if result.get("visualization_status") == "ready":
                    if not self.tutor.memory.repo.attach_guide(request.student_id, result["conversation_id"], result["guided_visualization"]):
                        raise TaskConflict("memory_deleted", "相关对话已删除，图解未保存")
                task, result = self.repo.save(task=task, receipt_id=receipt, memory_repo=self.tutor.memory.repo, status="completed", result=result,
                    context=context.model_dump() | {"document_versions": document_versions})
            return result
        except TaskConflict as error:
            if error.code in ('visualization_changed', 'document_changed','session_plan_changed') and 'task' in locals():
                try:
                    self.repo.save(task=task, receipt_id=receipt, memory_repo=self.tutor.memory.repo,
                        status='failed', result=self.conflict_reply(error))
                except TaskConflict:
                    pass
            return self.conflict_reply(error)
        except VisualizationError as error:
            result = {'reply':str(error), 'answer_status':'visualization_changed' if error.status == 409 else 'visualization_unavailable', 'step_advanced':False}
            if 'task' in locals():
                try:
                    self.repo.save(task=task, receipt_id=receipt, memory_repo=self.tutor.memory.repo, status='failed', result=result)
                except TaskConflict:
                    pass
            return result
        except Exception:
            # 失败请求不永久占着executing；保存时仍校验取消/删除版本。
            if "task" in locals() and task["status"] in ("ready", "executing"):
                try:
                    with self.tutor.memory.repo.unit_of_work():
                        # Planning can fail before the execution guard is
                        # defined. Failure cleanup needs only task/epoch
                        # ownership, not a successful resource/plan snapshot.
                        self.repo.guard(task['student_id'], task['session_id'],
                            task['id'], task['revision'], self.tutor.memory.repo)
                        self.repo.save(task=task, receipt_id=receipt, memory_repo=self.tutor.memory.repo, status="failed",
                            result={"reply": "本次回答失败，请重新发送问题。", "answer_status": "task_failed", "step_advanced": False})
                except TaskConflict:
                    pass
            raise
