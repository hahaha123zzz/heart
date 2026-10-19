"""原 API 的回合恢复入口；上游事件不能绕过宿主删除与版本检查。"""
import json
import os

from fastapi import APIRouter, Header, HTTPException, Query, Response
from fastapi.responses import StreamingResponse

from database.learning_tasks import TaskConflict, LearningTaskRepository
from .client import BackendUnavailable
from .task_projection import checked_task, replay_events, source_pointers

router = APIRouter(prefix="/api/chat", tags=["回合恢复"])


def conflict(error):
    status = 404 if error.code in {"task_not_found", "account_missing"} else 409 if error.code in {"task_conflict", "task_busy"} else 410
    return HTTPException(status, {"code": error.code, "message": str(error)})


@router.get("/requests/{request_id}")
def request_status(request_id: str, response: Response, student_id: str = Query(min_length=1, max_length=64),
                   session_id: str = Query(default="legacy", min_length=1, max_length=64)):
    from sqlalchemy import select
    from database.database import session_scope
    from database.models import TaskRequestRow

    response.headers["Cache-Control"] = "no-store"
    if not 1 <= len(request_id) <= 64:
        raise HTTPException(422, "请求编号长度无效")
    with session_scope() as db:
        task_id = db.scalar(select(TaskRequestRow.task_id).where(TaskRequestRow.student_id == student_id,
            TaskRequestRow.session_id == session_id, TaskRequestRow.request_id == request_id))
    if task_id is None:
        raise HTTPException(404, "请求不存在")
    try:
        row = LearningTaskRepository().get(student_id, session_id, task_id)
        row = checked_task(student_id, session_id, task_id, row["revision"], allow_active=True)
        if row["status"] not in {"ready", "executing"}:
            source_pointers(row["payload"], row["result"], row["context"].get("document_versions"))
        checked_task(student_id, session_id, task_id, row["revision"], allow_active=True)
        return {"task_id": task_id, "task_revision": row["revision"], "status": row["status"],
                "event_replay_enabled": os.getenv("DEEPTUTOR_TURN_SYNC", "0") == "1",
                "result": row["result"] if row["status"] not in {"ready", "executing"} else None}
    except TaskConflict as error:
        raise conflict(error) from error
    except (ValueError, OSError) as error:
        raise HTTPException(410, {"code": "source_changed", "message": "教材来源已变化，请重新提问"}) from error


@router.get("/tasks/{task_id}/events")
def task_events(task_id: str, task_revision: int = Query(ge=1),
                student_id: str = Query(min_length=1, max_length=64),
                session_id: str = Query(default="legacy", min_length=1, max_length=64),
                after_seq: int = Query(default=0, ge=0), last_event_id: str | None = Header(default=None)):
    if os.getenv("DEEPTUTOR_TURN_SYNC", "0") != "1":
        raise HTTPException(503, "上游回合恢复尚未启用")
    if not 1 <= len(task_id) <= 64:
        raise HTTPException(422, "任务编号长度无效")
    if last_event_id is not None:
        prefix = f"{task_id}:{task_revision}:"
        value = last_event_id.removeprefix(prefix)
        if not last_event_id.startswith(prefix) or not value.isascii() or not value.isdigit() or len(value) > 10:
            raise HTTPException(422, "Last-Event-ID 与当前任务版本不匹配")
        after_seq = max(after_seq, int(value))
    try:
        events = replay_events(student_id, session_id, task_id, task_revision, after_seq)
    except TaskConflict as error:
        raise conflict(error) from error
    except (BackendUnavailable, ValueError) as error:
        raise HTTPException(503, "DeepTutor 回合恢复暂不可用，请重试") from error
    body = "".join(f"id: {event['id']}\nevent: {event['event']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n" for event in events)
    return StreamingResponse(iter([body]) if body else iter([]), media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
