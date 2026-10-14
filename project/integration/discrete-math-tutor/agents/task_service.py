"""可恢复的澄清控制层；模型与执行通过回调，写事务不覆盖模型调用。"""
import re
from uuid import uuid4
from database.learning_tasks import LearningTaskRepository, TaskConflict
from models.chat_request import ChatRequest
from agents.task_context_builder import TaskContextBuilder
from knowledge.pdf_reader import resolve_selection
from knowledge.course import get_section
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

    def _context(self, request):
        recent = self.repo.recent(request.student_id, request.session_id)
        history = self.tutor.memory.get_history(request.student_id) if request.session_id == "legacy" else [
            item for row in recent for item in ({"role": "user", "content": row["payload"].get("message", "")},
                {"role": "assistant", "content": row["result"].get("reply", "")})]
        point = request.learning_goal or (recent[-1]["knowledge_point"] if recent else None) or self.tutor.memory.get_active_goal(request.student_id) or "图的基本概念"
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
            preferences=self.tutor.memory.get_profile(request.student_id).preferences)
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
            origin = row["context"].get("option_requests", {}).get(chosen)
            if option is None or origin is None:
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
        payload.update(message=merged, request_id=request.request_id, task_id=None, task_revision=None, selected_option=None)
        return ChatRequest.model_validate(payload)

    def run(self, request, executor, progress=None):
        try:
            # 模型未开始前确保账户；后续执行器在task_guard存在时不重建账户。
            if request.account_type == "test": self.tutor.memory.accounts.create_test_account(request.student_id, ttl_hours=24)
            elif request.account_type == "production": self.tutor.memory.ensure_student(request.student_id, account_type="production")
            else: raise ValueError("账户类型无效")
            # 灰度使用数据库中的账户类别，客户端不能把正式账户伪装成测试账户。
            account_type = self.repo.account_type(request.student_id)
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
            if replay is not None: return replay
            pending = self.repo.pending(request.student_id, request.session_id)
            task_id, revision = request.task_id, request.task_revision
            if task_id is None and pending and not re.search(r"换到|换个|改学|想学|重新提问", request.message):
                task_id, revision = pending["id"], pending["revision"]
            previous = self.repo.resume(request.student_id, request.session_id, task_id, revision, self.tutor.memory.repo) if task_id else None
            effective = self._resume(request, previous) if previous else request
            context, resolved, origins = self._context(effective)
            context.task_understanding_enabled = enabled
            if not self.policy.context or not enabled:
                if effective.visualization_target or effective.truth_table_target or effective.relation_target:
                    raise TaskConflict('task_disabled', '互动图提问需要开启任务上下文，本轮没有推进学习进度')
                context.objects = []
                context.preferences = {}
            point = context.knowledge_point
            epoch = self.tutor.memory.repo.memory_epoch(request.student_id, point)
            task, receipt, duplicate = self.repo.claim(student_id=request.student_id, session_id=request.session_id,
                request_id=request_key, payload=payload, point=point, epoch=epoch, memory_repo=self.tutor.memory.repo,
                task_id=task_id, revision=revision, ttl_seconds=self.ttl_seconds)
            if duplicate is not None: return duplicate
            def guard():
                self.repo.guard(task["student_id"], task["session_id"], task["id"], task["revision"], self.tutor.memory.repo)
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
                    saved_context = context.model_dump() | {"option_requests": origins}
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
                    context=context.model_dump(), routing=routing.model_dump(), payload=effective.model_dump())
                return None
            guard()
            result = executor(effective, context, resolved, intercept, guard, progress)
            if context.graph_snapshot:
                result['visualization_context'] = {k:v for k,v in context.graph_snapshot.items() if k != 'evaluation'}
            if context.truth_table_snapshot:
                result['truth_table_context'] = {k:v for k,v in context.truth_table_snapshot.items() if k != 'evaluation'}
            if context.relation_snapshot:
                result['relation_context']={k:v for k,v in context.relation_snapshot.items() if k!='evaluation'}
            if task["status"] in ("awaiting_clarification", "failed"): return result
            # 与最后一次保存使用相同工作单元检查，拒绝已删除/取消的迟到结果。
            with self.tutor.memory.repo.unit_of_work():
                guard()
                task, result = self.repo.save(task=task, receipt_id=receipt, memory_repo=self.tutor.memory.repo, status="completed", result=result)
            return result
        except TaskConflict as error:
            if error.code == 'visualization_changed' and 'task' in locals():
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
                        guard()
                        self.repo.save(task=task, receipt_id=receipt, memory_repo=self.tutor.memory.repo, status="failed",
                            result={"reply": "本次回答失败，请重新发送问题。", "answer_status": "task_failed", "step_advanced": False})
                except TaskConflict:
                    pass
            raise
