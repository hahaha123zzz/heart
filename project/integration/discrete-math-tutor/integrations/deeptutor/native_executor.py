"""宿主请求与原生持久回合的执行边界；不实现模型循环。"""
from contextlib import closing
from copy import deepcopy
import logging
import re
import time
from uuid import uuid4

from database.learning_tasks import LearningTaskRepository, TaskConflict
from knowledge.course_config import COURSE_ID, COURSE_TITLE, DEFAULT_GOAL
from .client import DeepTutorBackend, BackendUnavailable
from .native_contract import NativeTurnKey, NativeTurnStart, NativeTurnOptions, ADDITIONAL_TURN_FIELDS


def _pending(event):
    metadata = event.get("metadata") or {}
    value = (metadata.get("tool_metadata") or {}).get("ask_user") or metadata.get("ask_user")
    if value is None and event.get("type") == "wait_for_input":
        value = metadata if metadata.get("questions") else {"question": event.get("content") or "请补充信息"}
    if not isinstance(value, dict):
        return None
    questions = value.get("questions")
    if questions:
        value = {**value, "questions": [{**q, "prompt": q.get("prompt") or q.get("question") or "请补充信息"}
                                        for q in questions]}
    from agents.ask_user_contract import build_ask_user_payload
    payload, error = build_ask_user_payload(questions=value.get("questions"), intro=value.get("intro"),
                                          question=value.get("question"), options=value.get("options"))
    if payload is None:
        raise ValueError(error or "原生问题卡无效")
    return payload.to_dict()


def _clarification(payload):
    options = []
    questions = payload["questions"]
    if len(questions) == 1 and not questions[0].get("multi_select"):
        options = [{"id": "native-option-" + str(i), "label": option["label"]}
                   for i, option in enumerate(questions[0].get("options") or [])]
    return {"mode": "ask_user", "ask_user": payload, "questions": questions, "options": options}


def _public_result(metadata, task, binding, source_rows=(), *, capability=None):
    from .artifact_auth import url
    # 只公开交付物；原生物理路径、未知元数据与工具参数不返回页面。
    result = {key: deepcopy(metadata[key]) for key in ('response', 'title', 'transcript', 'output_mode') if key in metadata}
    capability = capability or binding.get('start', {}).get('capability')
    if capability == 'deep_question' and metadata.get('mode') != 'followup':
        from .native_delivery import public_quiz
        result.update(public_quiz(metadata))
    if metadata.get('renderer') and metadata.get('payload'):
        for key in ('schema_version','render_type','renderer','payload','presentation','interaction','fallback','code','analysis','review'):
            if key in metadata: result[key] = deepcopy(metadata[key])
    rows = [*metadata.get('workspace_items', []), *(item for item in source_rows if item.get('type') == 'workspace_item')]
    items = {}
    for item in rows:
        identifier = item.get('workspace_item_id')
        if not identifier or item.get('workspace_id') != binding.get('workspace_id'):
            continue
        public = {key: deepcopy(item[key]) for key in ('workspace_item_id','filename','mime_type','size_bytes','sha256','title','caption') if key in item}
        public['url'] = url(task['student_id'],task['session_id'],task['id'],identifier)
        items[identifier] = public
    if items:
        result['workspace_items'] = list(items.values())
        mapped = {item['filename']:item for item in items.values()}
        result['artifacts'] = [{key:value for key,value in artifact.items() if key in ('type','filename','content_type','label')}
            | {'url':mapped[artifact['filename']]['url']} for artifact in metadata.get('artifacts', [])
            if artifact.get('filename') in mapped]
    if result.get('artifacts') and (capability == 'math_animator'
                                  or str(metadata.get('render_type', '')).startswith('manim_')):
        result['render_type'] = metadata.get('render_type') or 'manim_' + metadata.get('output_mode', 'video')
        result['code'] = {key:deepcopy(value) for key,value in metadata.get('code', {}).items() if key in ('language','content')}
        result['timings'] = deepcopy(metadata.get('timings') or {})
        result['render'] = {key:deepcopy(value) for key,value in metadata.get('render', {}).items()
                            if key in ('quality','retry_attempts','retry_history')}
    if 'metadata' in metadata:
        result['metadata'] = {key:deepcopy(value) for key,value in metadata['metadata'].items()
                              if key in ('cost_summary','usage_summary','context_budget')}
    return result


class NativeTurnExecutor:
    def __init__(self, orchestrator, backend=None, repository=None):
        self.orchestrator = orchestrator
        self.memory = orchestrator.memory
        self.backend = backend or DeepTutorBackend(timeout=120)
        self.repo = repository or LearningTaskRepository()

    def run(self, request, progress=None, answer_event=None, answer_ready=None):
        request = request.model_copy(update={"request_id": request.request_id or str(uuid4())})
        timing_started = time.perf_counter()
        timing = logging.getLogger("heart.native_timing")
        def mark(name):
            timing.info("native_turn %s request=%s %.3f", name, request.request_id, time.perf_counter() - timing_started)
        try:
            if request.account_type == "test":
                self.memory.accounts.create_test_account(request.student_id, ttl_hours=24)
            elif request.account_type == "production":
                self.memory.ensure_student(request.student_id, account_type="production")
            else:
                raise ValueError("账户类型无效")
            self.repo.expire(request.student_id, request.session_id)
            mark("account_expire")
            payload = request.model_dump(mode="json")
            defaults = NativeTurnOptions().model_dump()
            for name in ADDITIONAL_TURN_FIELDS:
                if payload[name] == defaults[name]:
                    payload.pop(name)
            replay = self.repo.replay(request.student_id, request.session_id, request.request_id, payload, self.memory.repo)
            if replay and replay.get("answer_status") != "task_busy":
                return dict(replay, reader_action_replay=True) if replay.get('reader_actions') else replay
            if replay:
                task = self.repo.get(request.student_id, request.session_id, replay["task_id"])
                binding = task.get("context", {}).get("native_turn")
                if not binding:
                    return replay
                if not binding.get("turn_id"):
                    started = self.backend.native_start(binding["start"])
                    binding["turn_id"] = started.get("turn_id")
                    binding["workspace_id"] = started.get("workspace_id")
                    self._checkpoint(task, binding)
                if binding.get("pending_reply"):
                    self._submit_reply(task, binding)
                return self._consume(request, task, binding, progress, answer_event, answer_ready, started=timing_started)
            previous = None
            if request.task_id:
                previous = self.repo.resume(request.student_id, request.session_id, request.task_id,
                                            request.task_revision, self.memory.repo)
                if not previous.get("context", {}).get("native_turn"):
                    raise TaskConflict("legacy_task", "该待答任务来自旧执行器，请取消后重新提问。")
            if previous:
                binding = deepcopy(previous["context"]["native_turn"])
                from agents.task_service import TaskService
                clarification = previous["result"].get("clarification") or {}
                if request.selected_option is not None and not any(
                    item.get("id") == request.selected_option for item in clarification.get("options", [])):
                    raise TaskConflict("invalid_option", "问题卡选项已失效，请恢复最新任务。")
                answer = TaskService._selected_label(request, previous)
                task, receipt, duplicate = self.repo.claim(student_id=request.student_id, session_id=request.session_id,
                    request_id=request.request_id, payload=payload, point=previous["knowledge_point"], epoch=previous["epoch"],
                    memory_repo=self.memory.repo, task_id=request.task_id, revision=request.task_revision)
                if duplicate:
                    return duplicate
                task, _ = self.repo.save(task=task, receipt_id=receipt, status="executing", result={},
                    context={**previous["context"], "native_turn": binding}, memory_repo=self.memory.repo)
                binding["receipt_id"] = receipt
                binding["pending_reply"] = {"command_id": "reply-" + request.request_id, "text": answer}
                self._checkpoint(task, binding)
                self._submit_reply(task, binding)
            else:
                from knowledge.request_resources import resolve_resources
                resources = resolve_resources(student_id=request.student_id, session_id=request.session_id,
                    reader_location=request.reader_location, selection=request.selection,
                    exercise_target=request.exercise_target, visualization_target=request.visualization_target,
                    truth_table_target=request.truth_table_target, relation_target=request.relation_target)
                mark("resolve_resources")
                point = (request.learning_goal or DEFAULT_GOAL)[:200]
                epoch = self.memory.repo.memory_epoch(request.student_id, point)
                mark("memory_epoch")
                task, receipt, duplicate = self.repo.claim(student_id=request.student_id, session_id=request.session_id,
                    request_id=request.request_id, payload=payload, point=point, epoch=epoch,
                    memory_repo=self.memory.repo)
                mark("claim")
                if duplicate:
                    return duplicate
                from knowledge.pdf_reader import documents
                versions = {item["document_id"]: item["version"] for item in documents()}
                key = NativeTurnKey(student_id=request.student_id, course_id=COURSE_ID, session_id=request.session_id,
                    request_id=request.request_id, task_id=task["id"], task_revision=task["revision"]).model_dump()
                binding = {"key": key, "receipt_id": receipt, "after_seq": 0}
                task, _ = self.repo.save(task=task, receipt_id=receipt, status="executing", result={},
                    context={"native_turn": binding, "document_versions": versions}, memory_repo=self.memory.repo)
                mark("save_executing")
                from .native_grounding import prepare_selection
                sources, materials = prepare_selection(request, self.orchestrator)
                mark("prepare_selection")
                binding["sources"] = sources
                preferences = request.style_overrides.model_dump(exclude_none=True) if request.style_overrides else None
                native_options = request.model_dump(include=set(NativeTurnOptions.model_fields))
                if request.capability == 'immersive_reading' and not request.reading_viewport and request.reader_location:
                    native_options['reading_viewport'] = {'chapter_id': request.reader_location.chapter_id}
                start = NativeTurnStart(**key, course_title=COURSE_TITLE, content=request.message,
                    memory_epoch=epoch, material_versions=versions, teaching_preferences=preferences,
                    grounding=[obj.model_dump() for obj in resources.objects] + materials,
                    **native_options)
                binding["start"] = start.model_dump(mode="json")
                self._checkpoint(task, binding)
                started = self.backend.native_start(binding["start"])
                mark("native_start")
                binding["turn_id"] = started.get("turn_id")
                binding["workspace_id"] = started.get("workspace_id")
                self._checkpoint(task, binding)
                mark("checkpoint_after_start")
            binding["receipt_id"] = receipt
            self._checkpoint(task, binding)
            return self._consume(request, task, binding, progress, answer_event, answer_ready, started=timing_started)
        except TaskConflict as exc:
            return {"reply": str(exc), "answer_status": exc.code, "step_advanced": False,
                    **({"task_id": request.task_id, "task_revision": request.task_revision} if request.task_id else {})}
        except (ValueError, OSError) as exc:
            task = locals().get("task")
            if task:
                _, result = self.repo.save(task=task, receipt_id=locals().get("receipt") or locals().get("binding", {}).get("receipt_id"), status="failed",
                    result={"reply": "本轮资源校验未通过，未发布回答。", "answer_status": "validation_failed", "step_advanced": False},
                    context=task["context"], memory_repo=self.memory.repo)
                return result
            return {"reply": "本轮请求或资源无效。", "answer_status": "validation_failed", "step_advanced": False}
        except BackendUnavailable:
            # 保留 admission/游标收据，网络恢复后同一 request_id 只接原回合。
            task = locals().get("task")
            return {"reply": "原生运行服务暂未就绪；请使用原请求恢复，未切换到其他执行器。",
                    "answer_status": "native_unavailable", "step_advanced": False,
                    **({"task_id": task["id"], "task_revision": task["revision"]} if task else {})}

    def _submit_reply(self, task, binding):
        accepted = self.backend.native_command(binding["key"], **binding["pending_reply"])
        if not accepted.get("accepted"):
            raise TaskConflict("native_reply_rejected", "原生问题卡已结束或当前无法接收答复。")
        binding.pop("pending_reply")
        self._checkpoint(task, binding)

    def _checkpoint(self, task, binding):
        from database.database import session_scope
        from database.models import LearningTaskRow
        with session_scope(immediate=True) as db:
            row = self.repo._owned(db, task["student_id"], task["session_id"], task["id"])
            self.repo._live(row)
            if row.revision != task["revision"]:
                raise TaskConflict("task_conflict", "任务版本已变化，原生事件不能保存。")
            row.context = {**row.context, "native_turn": deepcopy(binding)}

    def _consume(self, request, task, binding, progress, answer_event, answer_ready, started=None):
        from .task_projection import checked_task
        def guard():
            checked_task(request.student_id, request.session_id, task["id"], task["revision"], allow_active=True)
        guard()
        first_event = True
        with closing(self.backend.native_events(binding["key"], after_seq=binding.get("after_seq", 0))) as events:
            for event in events:
                if first_event and started is not None:
                    logging.getLogger("heart.native_timing").info(
                        "native_turn first_event request=%s %.3f type=%s",
                        request.request_id, time.perf_counter() - started, event.get("type"))
                    first_event = False
                guard()
                seq = event.get("seq", 0)
                if type(seq) is not int or seq < binding.get("after_seq", 0):
                    raise ValueError("原生事件游标无效")
                binding["after_seq"] = seq
                if event.get("type") in ("stage_start", "stage_end", "progress", "tool_call") and progress:
                    label = event.get("stage") or event.get("source") or "原生执行"
                    progress(str(label), str(label), "正在原生运行时中执行，尚未正式保存。")
                pending = _pending(event)
                if pending:
                    self._checkpoint(task, binding)
                    result = {"engine": "deeptutor_app", "native_turn_id": binding.get("turn_id"),
                        "native_event_seq": seq, "reply": pending.get("intro") or pending["questions"][0]["prompt"],
                        "answer_status": "awaiting_clarification", "clarification": _clarification(pending),
                        "step_advanced": False}
                    _, saved = self.repo.save(task=task, receipt_id=binding["receipt_id"], status="awaiting_clarification",
                        result=result, context={**task["context"], "native_turn": binding}, memory_repo=self.memory.repo)
                    return saved
                if event.get("type") == "done":
                    break
        state = self.backend.native_status(binding["key"])
        if state.get("status") != "completed":
            result = {"engine": "deeptutor_app", "reply": "原生回合未正常完成，本轮没有发布正式回答。",
                      "answer_status": "native_" + str(state.get("status", "interrupted")), "step_advanced": False}
            _, saved = self.repo.save(task=task, receipt_id=binding["receipt_id"], status="failed", result=result,
                context={**task["context"], "native_turn": binding}, memory_repo=self.memory.repo)
            return saved
        from .native_delivery import public_quiz, publication_sources, project_reader_actions
        capability = state.get('capability') or binding.get('start', {}).get('capability', request.capability)
        metadata = state.get('result') or {}
        text = str(state.get("reply") or "").strip()
        if capability == 'deep_question' and metadata.get('mode') != 'followup':
            try:
                text = public_quiz(metadata)['response']
            except ValueError:
                _, result = self.repo.save(task=task, receipt_id=binding['receipt_id'], status='failed',
                    result={'engine':'deeptutor_app','reply':'题目尚未完整生成，本轮没有发布练习题。',
                            'answer_status':'incomplete_answer','step_advanced':False},
                    context={**task['context'],'native_turn':binding},memory_repo=self.memory.repo)
                return result
        from agents.agent_loop import LoopResult
        from agents.agent_loop_service import _publish_gate
        from agents.q3_navigation import LearningTarget
        outcome = LoopResult(final_text=text, completed=True,
            sources=publication_sources(binding, state, task['context'].get('document_versions') or {}))
        target = LearningTarget("native:" + task["id"], task["knowledge_point"])
        from models.chat_request import ChatRequest
        original = ChatRequest.model_validate(task['payload'])
        gate = _publish_gate(self.orchestrator, original, target, allow_model_knowledge=not bool(
            original.selection or original.exercise_target or re.search(r"教材原文|原书怎么说|引用原文|具体研究结果", original.message)))
        accepted, reason = gate(text, outcome)
        if not accepted:
            _, saved = self.repo.save(task=task, receipt_id=binding["receipt_id"], status="failed",
                result={"engine": "deeptutor_app", "reply": reason, "answer_status": "quality_rejected", "step_advanced": False},
                context={**task["context"], "native_turn": binding}, memory_repo=self.memory.repo)
            return saved
        guard()
        publication = getattr(outcome, "_publication", None) or {"reply": text, "pdf_references": [], "textbook_sources": []}
        result = {**publication, "engine": "deeptutor_app", "capability": capability,
            "native_turn_id": binding.get("turn_id"), "native_event_seq": binding.get("after_seq", 0),
            "native_result": _public_result(state.get("result") or {}, task, binding, state.get("sources") or [], capability=capability), "answer_status": "answered", "step_advanced": False}
        if state.get('mastery_events'):
            result['native_result']['mastery_events'] = deepcopy(state['mastery_events'])
        if state.get('reader_actions'):
            result['reader_actions'] = project_reader_actions(state['reader_actions'], task)
        with self.memory.repo.unit_of_work():
            guard()
            reference = {"native_result": result['native_result'],
                "pdf_references": result.get('pdf_references') or [],
                "textbook_sources": result.get('textbook_sources') or [], "section_title": task["knowledge_point"], "_native_assessment": {
                **binding["key"], "memory_epoch": task["epoch"], "material_versions": task["context"].get("document_versions", {})}}
            # 宿主这里只保存已发布页面投影；原生SessionStore独占模型历史。
            public_reference = {key:value for key,value in reference.items() if not key.startswith('_')}
            self.memory.repo.append_conversation(request.student_id, 'user', request.message,
                selection_ref=public_reference, session_id=request.session_id)
            result['conversation_id'] = self.memory.repo.append_conversation(
                request.student_id, 'assistant', result['reply'],
                selection_ref=reference, session_id=request.session_id)
            _, result = self.repo.save(task=task, receipt_id=binding["receipt_id"], status="completed", result=result,
                context={**task["context"], "native_turn": binding}, memory_repo=self.memory.repo)
        if answer_ready:
            answer_ready(result)
        return result


def run_native_turn(request, orchestrator, progress=None, answer_event=None, answer_ready=None):
    return NativeTurnExecutor(orchestrator).run(request, progress, answer_event, answer_ready)


def cancel_native_task(row, command_id):
    binding = row.get("context", {}).get("native_turn")
    if binding:
        return DeepTutorBackend(timeout=15).native_command(binding["key"], command_id=command_id)
    return None
