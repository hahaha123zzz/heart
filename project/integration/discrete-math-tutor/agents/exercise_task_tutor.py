"""聊天中的练习任务复用既有小题辅导，不再分类第二次或自行评分。"""
from uuid import uuid4
from sqlalchemy import select
from database.database import session_scope
from database.models import ExerciseDraftRow, ExerciseHelpRow
from agents.task_execution import build_execution


def explain_exercise(tutor, request, context, intercept, guard, progress=None):
    from practice_api import catalog, ai_parts, _GATE
    target = request.exercise_target
    data = catalog()
    if target.version != data['version']: raise ValueError('题库已更新，请重新选择')
    q = data['by_id'][target.question_id]
    part = next(p for p in q['parts'] if p['id'] == target.part_id)
    if progress: progress('routing', '理解小题问题', '确认小题与辅导需求')
    guard()
    task = tutor.conversation_router.route(request.message, context.knowledge_point,
        context.history, context.known_points, context=context)
    halted = intercept(task, context)
    if halted is not None: return halted
    execution = build_execution(request.message, task, context)
    current_id = f"exercise:{target.question_id}:{target.part_id}:{target.version}"
    if (task.intent in ('new_goal','switch_topic','off_task') or
            'practice' in execution.learning_intents or
            any(key != current_id for key in execution.target_refs)):
        return {'reply':'当前请求只针对所选小题；换知识点或生成新练习请另发问题。',
            'answer_status':'unsupported_task','step_advanced':False}
    with session_scope() as session:
        draft = session.scalar(select(ExerciseDraftRow).where(ExerciseDraftRow.student_id==request.student_id,
            ExerciseDraftRow.question_id==q['id'], ExerciseDraftRow.version==target.version))
        answers = {part['id']: draft.answers[part['id']]} if draft and part['id'] in draft.answers else {}
    if 'check_answer' in execution.learning_intents and not answers:
        return {'reply':'请先在练习页面填写并保存这个小题的答案，再让我检查。',
            'answer_status':'answer_required','step_advanced':False}
    if progress: progress('generating', '辅导指定小题', '只读取当前小题的作答与相关记录')
    guard()
    with _GATE:
        result = ai_parts(q,[part],answers,request.student_id,'hint' if execution.hint_only else 'explain',
            task_execution=execution,user_question=request.message)
    guard()
    if result.get('answer_status') == 'quality_rejected': return result
    point = q['knowledge_point']
    with tutor.memory.repo.unit_of_work():
        guard()
        reference={'guided_visualization':result['guided_visualization']} if result.get('guided_visualization') else None
        if result.get('pdf_references'):
            reference={**(reference or {}),'pdf_references':result['pdf_references'],
                'textbook_sources':result['textbook_sources'],'grounding_schema':'citation-grounding-v1'}
        if tutor.memory.append_exchange(request.student_id,request.message,result['reply'],selection_ref=reference,expected_point=point,task_guard=guard) is False:
            return {'reply':'相关记忆已删除，请重新提问。','answer_status':'memory_deleted','step_advanced':False}
        # 聊天获得提示也属于辅导，复用原有助教使用记录，避免后续评分误算独立作答。
        with session_scope() as session:
            session.add(ExerciseHelpRow(id=str(uuid4()),student_id=request.student_id,question_id=q['id'],
                version=target.version,part_id=part['id'],action='hint' if execution.hint_only else 'explain',
                level=1,answers=answers,response=result))
    return dict(result, answer_status='answered', routing=task.model_dump(), task_execution=execution.model_dump(),
        knowledge_point=point,step_advanced=False)
