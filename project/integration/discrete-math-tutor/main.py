"""离散数学助教 API；默认使用 24 小时自动过期的测试账户。 

启动：py -3.11 -m uvicorn main:app --reload
文档：http://127.0.0.1:8000/docs
"""

from __future__ import annotations

from typing import Optional
from pathlib import Path

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from database.database import init_db
from knowledge.figures import get_figure
from orchestrator import TutorOrchestrator
from web_api import router as web_router

app = FastAPI(title="离散数学 AI 助教", version="0.7.0")
app.include_router(web_router)
FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
orchestrator = TutorOrchestrator()

# 启动时建表 + 清理过期测试账户
init_db()
_PURGED = orchestrator.memory.cleanup_expired()


class ChatRequest(BaseModel):
    student_id: str = "default"
    message: str
    learning_goal: Optional[str] = None
    account_type: str = "test"


class TestAccountRequest(BaseModel):
    student_id: str
    ttl_hours: int = 24


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": "0.7.0",
        "mock_mode": orchestrator.llm.mock,
        "purged_expired_accounts": _PURGED,
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
def chat(request: ChatRequest):
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

def _run_turn(request: ChatRequest, progress=None):
    index = int.from_bytes(hashlib.sha256(request.student_id.encode()).digest()[:2], "big") % len(_turn_locks)
    if progress:
        progress("queued", "等待处理", "请求已接收")
    with _turn_locks[index]:
        return orchestrator.handle_turn(
            request.student_id, request.message, request.learning_goal,
            request.account_type, progress=progress,
        )

@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
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
                result = _run_turn(request, progress)
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
