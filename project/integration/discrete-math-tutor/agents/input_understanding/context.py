"""投影服务端已校验状态；不读取答案键、不另建状态存储。"""
from models.input_understanding import ContextHeader, ObjectReference


def pending_question(context):
    return ((context.tutoring or {}).get('progress') or {}).get('pending_question') or {}


def state_projection(context, request):
    from knowledge.course_config import COURSE_ID
    pending = pending_question(context)
    from agents.input_understanding.references import object_references
    refs = object_references(context)
    if pending.get('question_id'):
        refs.append(ObjectReference(ref_id='pending', kind='pending_question',
            canonical_id=pending['question_id'], status='resolved', origin='task',
            title=str(pending.get('prompt') or '')[:200]))
    header = ContextHeader(student_id=context.student_id, session_id=context.session_id, course_id=COURSE_ID,
        task_id=request.task_id, task_revision=request.task_revision,
        pending_question_id=pending.get('question_id'),
        pending_owner='host_formative' if pending else 'none',
        activity_target_id=(context.tutoring or {}).get('target_id'),
        reader_location=request.reader_location.model_dump() if request.reader_location else None)
    return header, refs


def public_context(context, references):
    pending = pending_question(context)
    return {'references': [ref.model_dump() for ref in references],
            'pending_question': {k:pending[k] for k in ('question_id','prompt','question_type','options') if k in pending},
            'history': context.history[-4:]}
