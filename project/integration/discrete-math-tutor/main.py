"""离散数学助教 API；学生数据由正式账号会话保护。

启动：py -3.11 -m uvicorn main:app --reload
文档：http://127.0.0.1:8000/docs
"""

from __future__ import annotations

from typing import Optional
from pathlib import Path

from fastapi import FastAPI, Depends, BackgroundTasks
from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import mimetypes
# Windows 注册表可能将 .js 标成 text/plain；模块与 PDF worker 需要正确 MIME。
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/javascript", ".mjs")
from pydantic import BaseModel, Field
from knowledge.pdf_reader import PDFSelection, validate_selection

from database.database import init_db
from database.repository import current_turn_id
from auth import router as auth_router, current_student_id, require_owner
from knowledge.figures import get_figure
from orchestrator import TutorOrchestrator
from web_api import router as web_router
from history_map import router as history_router, recover_pending_jobs

app = FastAPI(title="离散数学 AI 助教", version="0.9.0")
app.include_router(auth_router)
app.include_router(web_router)
app.include_router(history_router)
from practice_api import router as practice_router, recover_interrupted_submissions
app.include_router(practice_router)
FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
orchestrator = TutorOrchestrator()

# 启动时仅增量建表；不清理任何学生数据。
init_db()
recover_interrupted_submissions()
recover_pending_jobs()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    learning_goal: Optional[str] = None
    selection: Optional[PDFSelection] = None


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": "0.9.0",
        "mock_mode": orchestrator.llm.mock,
    }


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/figures/{figure_id}/image", include_in_schema=False)
def figure_image(figure_id: str):
    figure = get_figure(figure_id)
    if figure is None:
        raise HTTPException(404, "教材图片不存在或尚未审核")
    return FileResponse(figure.path, media_type="image/png")


@app.post("/api/chat")
def chat(request: ChatRequest, tasks: BackgroundTasks, student_id: str = Depends(current_student_id)):
    _validate_pdf_request(request)
    result, turn_id = _run_turn(student_id, request)
    from history_map import enqueue_turn
    tasks.add_task(enqueue_turn, student_id, turn_id)
    return result


# ---- 长期记忆查询 ----------------------------------------------------
@app.get("/api/students/{student_id}/profile")
def get_profile(student_id: str, auth_sid: str = Depends(current_student_id)):
    require_owner(student_id, auth_sid)
    return orchestrator.memory.get_profile(student_id).model_dump()


@app.get("/api/students/{student_id}/evidence")
def get_evidence(student_id: str, knowledge_point: Optional[str] = None,
                 auth_sid: str = Depends(current_student_id)):
    require_owner(student_id, auth_sid)
    return orchestrator.memory.list_evidence(student_id, knowledge_point)


@app.get("/api/students/{student_id}/misconceptions")
def get_misconceptions(student_id: str, knowledge_point: str,
                       auth_sid: str = Depends(current_student_id)):
    require_owner(student_id, auth_sid)
    return [
        m.model_dump()
        for m in orchestrator.memory.get_misconceptions(student_id, knowledge_point)
    ]


@app.get("/api/students/{student_id}/lesson")
def get_lesson(student_id: str, knowledge_point: str,
               auth_sid: str = Depends(current_student_id)):
    require_owner(student_id, auth_sid)
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
import uuid
from fastapi.responses import StreamingResponse

_turn_locks = [threading.Lock() for _ in range(64)]
_running_turns = set()

def _run_turn(student_id: str, request: ChatRequest, progress=None):
    index = int.from_bytes(hashlib.sha256(student_id.encode()).digest()[:2], "big") % len(_turn_locks)
    if progress:
        progress("queued", "等待处理", "请求已接收")
    with _turn_locks[index]:
        turn_id = str(uuid.uuid4())
        token = current_turn_id.set(turn_id)
        try:
            if request.selection:
                from agents.pdf_selection_tutor import explain_selection
                result = explain_selection(orchestrator, student_id, request.message,
                                           request.selection, progress)
            else:
                result = orchestrator.handle_turn(
                    student_id, request.message, request.learning_goal, progress=progress,
                )
            return result, turn_id
        finally:
            current_turn_id.reset(token)

@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest, student_id: str = Depends(current_student_id)):
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
                result, turn_id = _run_turn(student_id, request, progress)
                from history_map import enqueue_turn
                enqueue_turn(student_id, turn_id)
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
                yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                if event in ("done", "error"):
                    break
        finally:
            # 连接中断时已开始的工作继续保存结果，可通过对话历史恢复。
            disconnected = True

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


def _validate_pdf_request(request):
    if request.selection:
        try: validate_selection(request.selection)
        except ValueError as exc: raise HTTPException(422,str(exc)) from exc

@app.get('/api/pdf/documents/{document_id}/file', include_in_schema=False)
def textbook_pdf_file(document_id: str):
    from knowledge.pdf_reader import document, pdf_path
    record=document(document_id)
    if not record: raise HTTPException(404,'教材 PDF 不存在')
    return FileResponse(pdf_path(record),media_type='application/pdf',headers={'Cache-Control':'no-cache'})

@app.get('/api/pdf/crops/{crop_id}/image', include_in_schema=False)
def textbook_pdf_crop(crop_id: str, student_id: str = Depends(current_student_id)):
    from knowledge.pdf_reader import crop_path
    path=crop_path(crop_id)
    if not path: raise HTTPException(404,'教材选区不存在或已更新')
    return FileResponse(path,media_type='image/png')

@app.post('/api/pdf/selection/preview')
def preview_pdf_selection(selection: PDFSelection,
                          student_id: str = Depends(current_student_id)):
    from knowledge.pdf_reader import resolve_selection
    try: return resolve_selection(selection)['reference']
    except ValueError as exc: raise HTTPException(422,str(exc)) from exc
