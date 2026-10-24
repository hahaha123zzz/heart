"""教材助教 API；默认使用 24 小时自动过期的测试账户。

启动：py -3.11 -m uvicorn main:app --reload
文档：http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import os
from typing import Optional
from pathlib import Path

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import mimetypes
# Windows 注册表可能将 .js 标成 text/plain；模块与 PDF worker 需要正确 MIME。
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/javascript", ".mjs")
from pydantic import BaseModel, Field
from knowledge.pdf_reader import PDFSelection, validate_selection

from database.database import init_db
from knowledge.figures import get_figure
from orchestrator import TutorOrchestrator
from web_api import router as web_router

from memory.background_worker import memory_lifespan
from knowledge.course_config import COURSE_TITLE,COURSE_ID,PSYCHOLOGY

app = FastAPI(title=COURSE_TITLE+" AI 助教", version="0.8.0", lifespan=memory_lifespan)
app.include_router(web_router)
from integrations.deeptutor.router import router as deeptutor_router
app.include_router(deeptutor_router)
from integrations.deeptutor.recovery_router import router as turn_recovery_router
app.include_router(turn_recovery_router)
from practice_api import router as practice_router, recover_interrupted_submissions
app.include_router(practice_router)
from memory_api import router as memory_router
app.include_router(memory_router)
if not PSYCHOLOGY:
    from visualization_api import router as visualization_router
    app.include_router(visualization_router)
    from truth_table_api import router as truth_table_router
    app.include_router(truth_table_router)
    from relation_api import router as relation_router
    app.include_router(relation_router)
FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
from agents.intent_policy import IntentPolicy
# 配置错误在初始化业务服务前暴露，不静默开放灰度。
IntentPolicy.from_env()
from visualization.service import rollout_settings
rollout_settings()
orchestrator = TutorOrchestrator()
app.state.memory = orchestrator.memory
app.state.memory_llm = orchestrator.llm

# 启动时建表 + 清理过期测试账户
init_db()
recover_interrupted_submissions()
_PURGED = orchestrator.memory.cleanup_expired()


from models.chat_request import ChatRequest
from agents.task_context_builder import TaskContextBuilder


class TestAccountRequest(BaseModel):
    student_id: str
    ttl_hours: int = 24


@app.get("/health")
def health():
    from knowledge.inference_runtime import runtime_status
    return {
        "status": "ok",
        "course_id":COURSE_ID,
        "version": "0.8.0",
        "mock_mode": orchestrator.llm.mock,
        "purged_expired_accounts": _PURGED,
        "rag_runtime": runtime_status(),
        "memory_worker": app.state.memory_worker.status() if getattr(app.state, "memory_worker", None) else {"enabled": False, "running": False},
    }


@app.get("/", include_in_schema=False)
def home():
    import json
    from knowledge.course_config import public_course
    html=(FRONTEND_DIR/'index.html').read_text(encoding='utf-8')
    # Force browsers holding the prior chat bundle to load the current client.
    html=html.replace('app.js?v=20261019-markdown','app.js?v=20261024-new-chat')
    if PSYCHOLOGY:
        import re
        html=re.sub(r'<script src="/static/visualizations/(?:graph|truth-table|relation-closure|relation)\.js[^\"]*" defer></script>', '', html)
    config=json.dumps(public_course(),ensure_ascii=False).replace('<','\\u003c')
    return HTMLResponse(html.replace('<head>','<head><script>window.TutorCourse='+config+';</script>',1))


@app.get("/api/figures/{figure_id}/image", include_in_schema=False)
def figure_image(figure_id: str, sha256: str | None = None, version: str | None = None, document_id: str | None = None):
    figure = get_figure(figure_id)
    if figure is None:
        raise HTTPException(404, "教材图片不存在或原图身份已失效")
    if sha256 is not None and sha256 != figure.sha256:
        raise HTTPException(410, '教材图片版本已变化')
    if version is not None and version != figure.public().get('version'):
        raise HTTPException(410, '教材文档版本已变化')
    if document_id is not None and document_id != figure.public().get('document_id'):
        raise HTTPException(410, '原图不属于该教材文档')
    media_type = mimetypes.guess_type(figure.path.name)[0] or "application/octet-stream"
    return FileResponse(figure.path, media_type=media_type)


@app.post("/api/chat")
def chat(request: ChatRequest):
    _validate_pdf_request(request)
    return _run_turn(request)


# ---- 测试账户（test / production）------------------------------------
@app.post("/api/accounts/test")
def create_test_account(request: TestAccountRequest):
    orchestrator.memory.accounts.create_test_account(
        request.student_id, request.ttl_hours
    )
    return {
        "ok": True,
        "student_id": request.student_id,
        "account_type": "test",
        "ttl_hours": request.ttl_hours,
    }


@app.delete("/api/accounts/test/{student_id}")
def destroy_test_account(student_id: str):
    return {"ok": orchestrator.memory.accounts.destroy_test_account(student_id)}


# ---- 长期记忆查询 ----------------------------------------------------
@app.get("/api/students/{student_id}/profile")
def get_profile(student_id: str):
    return orchestrator.memory.get_profile(student_id).model_dump()


@app.get("/api/students/{student_id}/evidence")
def get_evidence(student_id: str, knowledge_point: Optional[str] = None):
    return orchestrator.memory.list_evidence(student_id, knowledge_point)


@app.get("/api/students/{student_id}/misconceptions")
def get_misconceptions(student_id: str, knowledge_point: str):
    return [
        m.model_dump()
        for m in orchestrator.memory.get_misconceptions(student_id, knowledge_point)
    ]


@app.get("/api/students/{student_id}/lesson")
def get_lesson(student_id: str, knowledge_point: str):
    plan = orchestrator.memory.get_lesson_plan(student_id, knowledge_point)
    return plan.model_dump() if plan else None


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)

# SSE 先建立事件队列再执行工作，避免丢失首个阶段；同一学生的写入串行。
import asyncio
import hashlib
import json
import threading
from fastapi.responses import StreamingResponse

_turn_locks = [threading.Lock() for _ in range(64)]
_running_turns = set()

def _run_turn(request: ChatRequest, progress=None, answer_ready=None, answer_event=None):
    index = int.from_bytes(hashlib.sha256(request.student_id.encode()).digest()[:2], "big") % len(_turn_locks)
    if progress:
        progress("queued", "等待处理", "请求已接收")
    with _turn_locks[index]:
        from agents.task_service import TaskService
        jobs = []
        def execute(*args, previous=None, **kwargs):
            return _execute_task_turn(*args, previous=previous, **kwargs, visualization_jobs=jobs)
        result = TaskService(orchestrator).run(request, execute, progress,
            visualization_jobs=jobs, answer_ready=answer_ready, answer_event=answer_event)
        from integrations.deeptutor.session_sync import sync_completed_session
        from integrations.deeptutor.task_projection import sync_saved_turn
        result = sync_completed_session(request, result)
        return sync_saved_turn(request, result)


def _execute_task_turn(request, context, resolved, intercept, guard, progress, *, visualization_jobs=None, previous=None, q5_binding=None):
    explicit_target=request.visualization_target or request.truth_table_target or request.relation_target
    from agents.selection_loop import enabled as selection_loop_enabled
    if (selection_loop_enabled() and not request.exercise_target and not explicit_target
            and (context.selection_scope is not None
                 or (request.selection is not None and request.selection.kind == 'text'))):
        from agents.agent_loop_service import run_agent_loop_turn
        return run_agent_loop_turn(orchestrator=orchestrator, request=request, context=context,
            resolved=resolved, guard=guard, progress=progress, previous=previous,
            visualization_jobs=visualization_jobs)
    if os.getenv("LOCAL_AGENT_LOOP_ENABLED", "0") == "1" and not any(
            (request.selection, request.exercise_target, explicit_target)):
        from agents.agent_loop_service import run_agent_loop_turn
        return run_agent_loop_turn(orchestrator=orchestrator, request=request,
            context=context, resolved=resolved, intercept=intercept, guard=guard,
            progress=progress, previous=previous, q5=q5_binding)
    if explicit_target and explicit_target.action:
        routing = TaskContextBuilder.button_task(context, explicit_target.action)
        return orchestrator.handle_turn(request.student_id, request.message, request.learning_goal,
            request.account_type, progress=progress, task_context=context,
            precomputed_routing=routing, routing_interceptor=intercept, task_guard=guard, visualization_jobs=visualization_jobs)
    if request.exercise_target:
        from agents.exercise_task_tutor import explain_exercise
        return explain_exercise(orchestrator, request, context, intercept, guard, progress)
    if request.selection:
        from agents.pdf_selection_tutor import explain_selection
        return explain_selection(orchestrator, request.student_id, request.message,
            request.selection, request.account_type, progress, session_id=request.session_id,
            request_id=request.request_id, reader_location=request.reader_location,
            task_context=context, resolved_selection=resolved, routing_interceptor=intercept, task_guard=guard, visualization_jobs=visualization_jobs)
    return orchestrator.handle_turn(request.student_id, request.message, request.learning_goal,
        request.account_type, progress=progress, task_context=context,
        routing_interceptor=intercept, task_guard=guard, visualization_jobs=visualization_jobs)

@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    _validate_pdf_request(request)
    async def events():
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue()
        current = None
        sequence = 0
        disconnected = False

        def emit(event, data):
            if not disconnected:
                loop.call_soon_threadsafe(queue.put_nowait, (event, data))

        def progress(stage, label, detail=""):
            nonlocal current, sequence
            if current and current["stage"] != stage:
                emit("progress", {**current, "status": "completed"})
            if not current or current["stage"] != stage:
                sequence += 1
            current = {"stage": stage, "label": label, "detail": detail, "order": sequence}
            emit("progress", {**current, "status": "running"})

        def work():
            try:
                result = _run_turn(request, progress, answer_ready=lambda result: emit("answer", result), answer_event=emit)
                if current:
                    emit("progress", {**current, "status": "completed"})
                emit("done", result)
            except Exception:
                # 不向浏览器传递可能包含服务配置或凭据的异常文本。
                import logging
                logging.getLogger(__name__).exception("Chat turn failed")
                emit("error", {"message": "本次回答失败，请稍后重试；详细原因请查看服务端日志。"})

        task = asyncio.create_task(asyncio.to_thread(work))
        _running_turns.add(task)
        task.add_done_callback(_running_turns.discard)
        try:
            while True:
                try:
                    event, data = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                identifier = ""
                if event == "done" and data.get("task_id") and data.get("task_revision"):
                    identifier = f"id: {data['task_id']}:{data['task_revision']}:2\n"
                yield f"{identifier}event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                if event in ("done", "error"):
                    break
        finally:
            # 连接中断时已开始的工作继续保存结果，可通过对话历史恢复。
            disconnected = True

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


def _validate_pdf_request(request):
    try:
        if request.relation_target:
            from visualization.relation import RelationService
            from visualization.service import VisualizationError
            try:RelationService().snapshot(request.relation_target,request.student_id,request.session_id)
            except VisualizationError as exc:raise HTTPException(exc.status,str(exc)) from exc
        if request.truth_table_target:
            from visualization.truth_table import TruthTableService
            from visualization.service import VisualizationError
            try:
                TruthTableService().snapshot(request.truth_table_target, request.student_id, request.session_id)
            except VisualizationError as exc:
                raise HTTPException(exc.status, str(exc)) from exc
        if request.visualization_target:
            from visualization.service import VisualizationService, VisualizationError
            try:
                VisualizationService().snapshot(request.visualization_target, request.student_id, request.session_id)
            except VisualizationError as exc:
                raise HTTPException(exc.status, str(exc)) from exc
        if request.selection:
            record = validate_selection(request.selection)
            if request.reader_location and request.reader_location.chapter_id != record['chapter_id']:
                raise ValueError('选区与教材章节不一致，请重新选择')
        if request.reader_location or request.exercise_target:
            # 在SSE建立连接前检查对象有效性，避免失效题号变成流中的通用错误。
            TaskContextBuilder().build(student_id=request.student_id, message=request.message,
                reader_location=request.reader_location, exercise_target=request.exercise_target)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc

@app.get('/api/pdf/documents/{document_id}/file', include_in_schema=False)
def textbook_pdf_file(document_id: str):
    from knowledge.pdf_reader import document, pdf_path
    record=document(document_id)
    if not record: raise HTTPException(404,'教材 PDF 不存在')
    return FileResponse(pdf_path(record),media_type='application/pdf',headers={'Cache-Control':'no-cache'})

@app.get('/api/pdf/crops/{crop_id}/image', include_in_schema=False)
def textbook_pdf_crop(crop_id: str):
    from knowledge.pdf_reader import crop_path
    path=crop_path(crop_id)
    if not path: raise HTTPException(404,'教材选区不存在或已更新')
    return FileResponse(path,media_type='image/png')

@app.post('/api/pdf/selection/preview')
def preview_pdf_selection(selection: PDFSelection):
    from knowledge.pdf_reader import resolve_selection
    try: return resolve_selection(selection)['reference']
    except ValueError as exc: raise HTTPException(422,str(exc)) from exc


class TaskCancelRequest(BaseModel):
    student_id: str = Field(min_length=1, max_length=64)
    session_id: str = Field(default="legacy", min_length=1, max_length=64)
    task_revision: int = Field(ge=1)


@app.get("/api/chat/tasks/pending")
def pending_task(student_id: str, session_id: str = "legacy"):
    from database.learning_tasks import LearningTaskRepository
    tasks = LearningTaskRepository()
    tasks.expire(student_id, session_id)
    from agents.intent_policy import IntentPolicy
    if not IntentPolicy.from_env().can_clarify(student_id, tasks.account_type(student_id)):
        changed = tasks.invalidate_pending(student_id, session_id)
        return {"pending": None, "notice": "上一个待补充问题已失效，请完整重新提问。" if changed else ""}
    row = tasks.pending(student_id, session_id)
    if row is None: return {"pending": None}
    if orchestrator.memory.repo.memory_epoch(student_id, row["knowledge_point"]) != row["epoch"]:
        return {"pending": None}
    pending = dict(row["result"])
    # Internal model/tool protocol stays server-side; the page only needs the card.
    pending.pop("loop_state", None)
    pending.pop("loop_events", None)
    return {"pending": pending}


@app.delete("/api/chat/tasks/{task_id}")
def cancel_task(task_id: str, request: TaskCancelRequest):
    from database.learning_tasks import LearningTaskRepository, TaskConflict
    from agents import task_cancellation
    task_cancellation.cancel(task_id)
    try:
        return LearningTaskRepository().cancel(request.student_id, request.session_id, task_id, request.task_revision)
    except TaskConflict as exc:
        return {"reply": str(exc), "answer_status": exc.code, "step_advanced": False}
