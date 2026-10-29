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


@router.post('/authorize-assessment')
def authorize_native_assessment(payload: NativeTaskCheck):
    """持久题卡独立于聊天TTL；不授予继续生成旧回合的权限。"""
    from database.models import ConversationRow, PDFCitationRow, Student, LearningTaskRow
    from database.repository import Repository
    from database.learning_tasks import now
    from .native_contract import NativeTurnKey
    from knowledge.pdf_reader import documents
    key = payload.model_dump(include=set(NativeTurnKey.model_fields))
    with session_scope() as db:
        records = db.execute(select(PDFCitationRow).join(ConversationRow,
            ConversationRow.id == PDFCitationRow.conversation_id).where(
            ConversationRow.student_id == payload.student_id, ConversationRow.session_id == payload.session_id,
            ConversationRow.role == 'assistant')).scalars()
        projection = next((row for row in records if all((row.reference.get('_native_assessment') or {}).get(k) == v
            for k, v in key.items())), None)
        if projection is None:
            # 首次登记还没有发布题卡，只能使用未过期的原任务。
            return authorize_native_task(payload)
        reference = projection.reference
        student = db.get(Student, payload.student_id)
        task = db.get(LearningTaskRow, payload.task_id)
        if (payload.course_id != COURSE_ID or student is None
                or (student.expires_at is not None and student.expires_at <= now())
                or (task is not None and (task.student_id != payload.student_id or task.session_id != payload.session_id
                    or task.status == 'cancelled'
                    or (task.revision != payload.task_revision and task.status != 'expired')))):
            raise HTTPException(409, detail={'code': 'assessment_owner_changed'})
        binding = reference['_native_assessment']
        point = task.knowledge_point if task else reference.get('section_title', '')
        if binding.get('memory_epoch') != payload.memory_epoch or Repository().memory_epoch(payload.student_id, point) != payload.memory_epoch:
            raise HTTPException(409, detail={'code': 'memory_deleted'})
        frozen = binding.get('material_versions')
        if not frozen and task is not None:
            frozen = (task.context or {}).get('document_versions')
        frozen = frozen or {s['document_id']: s['version']
            for card in reference.get('learning_cards', []) for s in card.get('source_refs', [])}
        published = {row['document_id']: row['version'] for row in documents()}
        if not frozen or frozen != payload.material_versions or any(published.get(k) != v for k, v in frozen.items()):
            raise HTTPException(409, detail={'code': 'source_changed'})
        if not binding.get('material_versions'):
            projection.reference = {**reference, '_native_assessment': {**binding, 'material_versions': frozen}}
    return {'authorized': True, **payload.model_dump()}


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
