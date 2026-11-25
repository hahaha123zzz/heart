"""已发布文件/普通题目的持久收据；不授权重新运行过期任务。"""
from copy import deepcopy
import os
from .native_contract import NativeTurnKey


def published_binding(student_id,session_id,task_id,*,item_id=None,question_id=None):
    from sqlalchemy import select
    from database.database import session_scope
    from database.models import Student,ConversationRow,PDFCitationRow,LearningTaskRow
    from database.learning_tasks import TaskConflict,now
    from knowledge.course_config import COURSE_ID
    with session_scope() as db:
        student=db.get(Student,student_id)
        task=db.get(LearningTaskRow,task_id)
        if (student is None or student.expires_at is not None and student.expires_at<=now()
                or task is not None and (task.student_id!=student_id or task.session_id!=session_id or task.status=='cancelled')):
            raise TaskConflict('publication_unavailable','已发布内容不存在或授权已失效')
        rows=db.execute(select(PDFCitationRow.reference,ConversationRow.created_at).join(ConversationRow,
            ConversationRow.id==PDFCitationRow.conversation_id).where(ConversationRow.student_id==student_id,
            ConversationRow.session_id==session_id,ConversationRow.role=='assistant'))
        for reference,created_at in rows:
            proof=reference.get('_native_assessment') or {}
            if proof.get('task_id')!=task_id or created_at<student.created_at:
                continue
            key=NativeTurnKey.model_validate({name:proof.get(name) for name in NativeTurnKey.model_fields}).model_dump()
            if key['student_id']!=student_id or key['session_id']!=session_id or key['course_id']!=COURSE_ID:
                continue
            result=reference.get('native_result') or {}
            if item_id is not None and not any(item.get('workspace_item_id')==item_id for item in result.get('workspace_items',[])):
                continue
            if question_id is not None and not any((item.get('qa_pair') or {}).get('question_id')==question_id
                    for item in (result.get('summary') or {}).get('results',[])):
                continue
            return {'key':key}
    raise TaskConflict('publication_unavailable','该内容没有已发布对话收据')


def public_reference(reference,student_id,session_id):
    public=deepcopy({key:value for key,value in reference.items() if not key.startswith('_')})
    proof=reference.get('_native_assessment') or {}
    result=public.get('native_result') or {}
    items=result.get('workspace_items') or []
    if (not items or proof.get('student_id')!=student_id or proof.get('session_id')!=session_id
            or not proof.get('task_id') or len(os.getenv('DEEPTUTOR_BRIDGE_TOKEN',''))<32):
        return public
    from .artifact_auth import url
    by_name={}
    for item in items:
        item['url']=url(student_id,session_id,proof['task_id'],item['workspace_item_id'])
        by_name[item['filename']]=item['url']
    for artifact in result.get('artifacts') or []:
        if artifact.get('filename') in by_name:
            artifact['url']=by_name[artifact['filename']]
    return public
