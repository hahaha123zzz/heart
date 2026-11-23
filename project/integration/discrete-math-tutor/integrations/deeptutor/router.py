"""宿主接入入口；课程、权限和上游身份由服务端确定。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .client import BackendUnavailable, DeepTutorBackend

router = APIRouter(prefix="/api/deeptutor", tags=["deeptutor"])


class HostSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    student_id: str = Field(min_length=1, max_length=64)
    session_id: str = Field(default="legacy", min_length=1, max_length=64)


@router.post("/session")
def bind_session(request: HostSessionRequest):
    from sqlalchemy import select
    from database.database import session_scope
    from database.models import Student

    with session_scope() as db:
        exists = db.scalar(select(Student.student_id).where(Student.student_id == request.student_id))
    if exists is None:
        raise HTTPException(404, "学生账户不存在")
    try:
        return DeepTutorBackend().bind_session(request.student_id, request.session_id)
    except (BackendUnavailable, ValueError) as exc:
        raise HTTPException(503, "DeepTutor 会话服务暂未就绪") from exc


@router.get("/status")
def backend_status():
    try:
        return DeepTutorBackend().status()
    except ValueError as exc:
        raise HTTPException(503, "DeepTutor 本机服务配置无效") from exc


@router.get("/capabilities")
def backend_capabilities():
    try:
        return {"capabilities": DeepTutorBackend().capabilities()}
    except (BackendUnavailable, ValueError) as exc:
        raise HTTPException(503, "DeepTutor 能力服务暂未就绪") from exc


@router.post("/catalog")
def native_catalog(request: HostSessionRequest):
    from .runtime_config import native_enabled
    if not native_enabled():
        return {"enabled": False, "capabilities": [], "tools": [], "extensions": [], "resources": {}}
    from database.database import session_scope
    from database.models import Student
    from knowledge.course_config import COURSE_ID, COURSE_TITLE
    with session_scope() as db:
        if db.get(Student, request.student_id) is None:
            raise HTTPException(404, "学生账户不存在")
    try:
        return DeepTutorBackend().native_catalog({**request.model_dump(),
            "course_id": COURSE_ID, "course_title": COURSE_TITLE})
    except (BackendUnavailable, ValueError) as exc:
        raise HTTPException(503, "原生能力和工具目录暂未就绪") from exc


@router.get("/tasks/{task_id}/artifacts/{item_id}")
def native_artifact(task_id: str, item_id: str, student_id: str, session_id: str, signature: str):
    import json
    import os
    from urllib.request import Request
    from fastapi.responses import StreamingResponse
    from database.learning_tasks import LearningTaskRepository, TaskConflict
    from .artifact_auth import verify
    try:
        # 先验证服务端签发的单文件授权；猜中任何身份/任务/文件 ID 都不能下载。
        if not verify(student_id,session_id,task_id,item_id,signature):
            raise HTTPException(403, '文件授权签名无效')
        task = LearningTaskRepository().get(student_id, session_id, task_id)
        binding = task.get('context', {}).get('native_turn') or {}
        items = (task.get('result', {}).get('native_result') or {}).get('workspace_items') or []
        if task['status'] == 'cancelled' or not binding or not any(item.get('workspace_item_id') == item_id for item in items):
            raise HTTPException(404, "文件不属于该对话")
        backend = DeepTutorBackend(timeout=30)
        token = os.environ.get('DEEPTUTOR_BRIDGE_TOKEN', '')
        if len(token) < 32:
            raise ValueError('bridge token missing')
        response = backend.opener.open(Request(backend.base_url+'/internal/heart/native/artifact',
            data=json.dumps({**binding['key'], 'item_id': item_id}).encode(),
            headers={'Content-Type':'application/json','X-Heart-Bridge-Token':token}), timeout=30)
        size = int(response.headers.get('Content-Length', '0'))
        if not 0 < size <= 256 * 1024 * 1024:
            response.close()
            raise HTTPException(413, "文件大小超过预览限制")
        def chunks():
            try:
                remaining = size
                while remaining:
                    chunk = response.read(min(1024*1024, remaining))
                    if not chunk: break
                    remaining -= len(chunk)
                    yield chunk
            finally:
                response.close()
        return StreamingResponse(chunks(), media_type=response.headers.get('Content-Type','application/octet-stream'),
            headers={'Content-Length':str(size),'X-Content-Type-Options':'nosniff','Cache-Control':'private, no-store',
                'Content-Disposition':response.headers.get('Content-Disposition','attachment'),
                'Content-Security-Policy':"sandbox; default-src 'none'; img-src data: blob:; media-src 'self' blob:; style-src 'unsafe-inline'"})
    except TaskConflict as exc:
        raise HTTPException(404, '对话文件不存在') from exc
    except (OSError, BackendUnavailable, ValueError) as exc:
        raise HTTPException(503, '原生文件暂不可用或授权已失效') from exc


from .native_contract import MemoryOperation


class HostMemoryRequest(HostSessionRequest, MemoryOperation):
    pass


@router.post('/memory')
def native_memory(request: HostMemoryRequest):
    from contextlib import nullcontext
    from copy import deepcopy
    import time
    from uuid import uuid4
    from sqlalchemy import select
    from database.database import session_scope
    from database.models import Student, LearningTaskRow
    from database.learning_tasks import LearningTaskRepository, ACTIVE, TaskConflict
    from database.task_locks import student_turn_lock
    from knowledge.course_config import COURSE_ID, COURSE_TITLE
    from .runtime_config import native_enabled

    if not native_enabled():
        if request.action == 'overview':
            return {'enabled': False}
        raise HTTPException(503, '原生记忆尚未启用')
    with session_scope() as db:
        if db.get(Student, request.student_id) is None:
            raise HTTPException(404, '学生账户不存在')
    mutating = request.action in ('write', 'delete_entry')
    with student_turn_lock(request.student_id) if mutating else nullcontext():
        backend = DeepTutorBackend(timeout=30)
        try:
            if mutating:
                with session_scope() as db:
                    tasks = [{'id': row.id, 'session_id': row.session_id,
                              'revision': row.revision, 'context': deepcopy(row.context)}
                             for row in db.scalars(select(LearningTaskRow).where(
                                 LearningTaskRow.student_id == request.student_id,
                                 LearningTaskRow.status.in_(ACTIVE)))]
                for task in tasks:
                    binding = (task['context'] or {}).get('native_turn')
                    if binding and binding.get('turn_id'):
                        backend.native_command(binding['key'], command_id='memory-edit-' + str(uuid4()))
                        deadline = time.monotonic() + 15
                        while backend.native_status(binding['key']).get('status') not in ('completed','failed','cancelled'):
                            if time.monotonic() >= deadline:
                                raise HTTPException(409, '请等待当前回合停止后再修改记忆')
                            time.sleep(.1)
                    LearningTaskRepository().cancel(request.student_id, task['session_id'], task['id'], task['revision'])
            return backend.native_memory({**request.model_dump(), 'course_id': COURSE_ID, 'course_title': COURSE_TITLE})
        except TaskConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except (BackendUnavailable, ValueError) as exc:
            raise HTTPException(503, '原生记忆暂未就绪，修改未确认') from exc
