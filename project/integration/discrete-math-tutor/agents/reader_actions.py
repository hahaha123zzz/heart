"""阅读器动作回执保存于既有任务结果；不新增表，不改变学习状态。"""
from copy import deepcopy
import hashlib
from sqlalchemy import select, update
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from database.database import session_scope
from database.models import LearningTaskRow, TaskRequestRow
from database.learning_tasks import LearningTaskRepository, TaskConflict, now


class ReaderActionReceipt(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    student_id: str = Field(min_length=1, max_length=64)
    session_id: str = Field(min_length=1, max_length=64)
    task_revision: int = Field(ge=1)
    action_id: str = Field(min_length=1, max_length=64)
    status: Literal['applied', 'rejected']
    document_id: str = Field(default='', max_length=200)
    version: str = Field(default='', max_length=200)
    page: int | None = Field(default=None, ge=1)
    reason: str = Field(default='', max_length=200)


def acknowledge(task_id, receipt, memory_repo):
    from knowledge.pdf_reader import document, pdf_path
    repository = LearningTaskRepository()
    with session_scope(immediate=True) as session:
        row = repository._owned(session, receipt.student_id, receipt.session_id, task_id)
        if row.revision != receipt.task_revision or row.status != 'completed' or row.expires_at <= now():
            raise TaskConflict('task_conflict', '旧任务动作不再执行。')
        if memory_repo.memory_epoch(row.student_id, row.knowledge_point) != row.epoch:
            raise TaskConflict('memory_deleted', '相关任务已失效。')
        newer = session.scalar(select(LearningTaskRow.id).where(
            LearningTaskRow.student_id == row.student_id, LearningTaskRow.session_id == row.session_id,
            LearningTaskRow.created_at > row.created_at).limit(1))
        if newer:
            raise TaskConflict('task_conflict', '新任务已开始，不再接受旧页面动作。')
        result = deepcopy(row.result)
        action = next((a for a in result.get('reader_actions', []) if a['action_id'] == receipt.action_id), None)
        if not action or action['task_id'] != task_id or result.get('answer_status') != 'answered':
            raise TaskConflict('task_conflict', '没有该任务的有效页面动作。')
        if action['status'] != 'requested':
            return action
        if receipt.status == 'applied':
            record = document(action['document_id'])
            try:
                valid_file = bool(record and record['version'] == action['version'] and
                                  hashlib.sha256(pdf_path(record).read_bytes()).hexdigest() == action['version'])
            except OSError:
                valid_file = False
            if (receipt.document_id, receipt.version, receipt.page) != (
                action['document_id'], action['version'], action['page']) or not valid_file:
                raise TaskConflict('document_changed', '实际到达页或教材版本不匹配。')
        action.update(status=receipt.status, reason=receipt.reason)
        row.result = result
        session.execute(update(TaskRequestRow).where(TaskRequestRow.task_id == task_id).values(result=result))
        return deepcopy(action)
