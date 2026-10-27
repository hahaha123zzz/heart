"""原生接收端回查宿主任务；私有凭据不替代学生/任务/删除版本检查。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from database.database import session_scope
from database.learning_tasks import TaskConflict
from database.models import TaskRequestRow
from knowledge.course_config import COURSE_ID
from .native_contract import NativeTaskCheck
from .session_bridge import require_bridge_token
from .task_projection import checked_task

router = APIRouter(prefix='/internal/heart/native', dependencies=[Depends(require_bridge_token)])


@router.post('/authorize')
def authorize_native_task(payload: NativeTaskCheck):
    try:
        if payload.course_id != COURSE_ID:
            raise TaskConflict('course_mismatch', '宿主课程不匹配')
        row = checked_task(payload.student_id, payload.session_id, payload.task_id,
                           payload.task_revision, allow_active=True)
        with session_scope() as db:
            receipt = db.scalar(select(TaskRequestRow).where(
                TaskRequestRow.student_id == payload.student_id, TaskRequestRow.session_id == payload.session_id,
                TaskRequestRow.request_id == payload.request_id, TaskRequestRow.task_id == payload.task_id))
            if receipt is None:
                raise TaskConflict('request_conflict', '请求不属于当前宿主任务')
        if payload.memory_epoch != row['epoch']:
            raise TaskConflict('memory_deleted', '宿主记忆版本不匹配')
        versions = row.get('context', {}).get('document_versions')
        if versions is None or versions != payload.material_versions:
            raise TaskConflict('source_changed', '宿主教材快照不匹配')
        from knowledge.pdf_reader import documents
        published = {item['document_id']: item['version'] for item in documents()}
        if any(published.get(key) != version for key, version in versions.items()):
            raise TaskConflict('source_changed', '教材版本已变化')
    except TaskConflict as exc:
        raise HTTPException(409, detail={'code': exc.code, 'message': str(exc)}) from exc
    return {'authorized': True, **payload.model_dump()}
