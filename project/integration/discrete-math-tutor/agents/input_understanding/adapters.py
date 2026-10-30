"""现有入口消费统一理解；不持有另一份业务状态。"""
from agents.input_understanding.service import explicit_switch
from agents.input_understanding.context import pending_question


def preserve_activity(context, request):
    if (context.input_mode != 'active' or not pending_question(context) or explicit_switch(request)
            or any((request.selection, request.exercise_target, request.visualization_target,
                    request.truth_table_target, request.relation_target))):
        return
    old = context.tutoring
    context.knowledge_point = old.get('topic') or context.knowledge_point
    context.activity_target = {'target_id': old.get('target_id') or f'kp:{context.knowledge_point}',
        'name':context.knowledge_point, 'chapter_id':old.get('chapter_id'),
        'section_id':next((s.get('section_id') for s in old.get('pending_sources',[]) if s.get('section_id')),None)}
    # 阅读游标仍在请求中作为检索偏好；它不是用户切换教学目标的指令。
    context.course_navigation = None


def active_turn(context):
    return context.input_understanding if getattr(context,'input_mode','off') == 'active' else None


def resume_understanding(previous, request, request_key):
    """沿已授权暂停任务恢复；本次用户原话与原任务要求分别保存。"""
    state=(previous or {}).get('context') or {}
    if not (state.get('loop_state') or {}).get('pending_tool_call_id') or not state.get('input_understanding'):
        return None
    from models.input_understanding import GroundedTurn,InputEnvelope
    from agents.input_understanding.rules import normalize
    turn=GroundedTurn.model_validate(state['input_understanding'])
    normalized,positions=normalize(request.message)
    value=turn.model_dump()
    value['reply_envelope']=InputEnvelope(request_id=request_key,raw_text=request.message,
        normalized_text=normalized or request.message,source_positions=positions or list(range(len(request.message))),
        input_kind='clarification').model_dump()
    return GroundedTurn.model_validate(value)


def legacy_routing(context):
    """仅投影确定的单项教学请求；闲聊和未绑定指代仍走原路由。"""
    import re
    turn=active_turn(context)
    if not turn or len(turn.tasks)!=1 or turn.resolution_status!='resolved':
        return None
    task=turn.tasks[0]
    intent={'explain_content':'explain','compare_content':'compare','provide_hint':'hint'}.get(task.action)
    if intent is None or not re.search(r'什么是|是什么|^(?:请)?解释|比较|区别|只(?:给|要).{0,6}提示',turn.envelope.raw_text):
        return None
    from models.task_understanding import TaskUnderstanding
    objects={obj.id for obj in context.objects}
    ref=next((r for r in turn.references if r.ref_id==task.target_ref),None)
    targets=[ref.canonical_id] if ref and ref.canonical_id in objects else []
    return TaskUnderstanding(student_move='question',intent='continue',confidence=1.,
        learning_intents=[intent],target_refs=targets,answer_constraints=list(task.constraints),
        rewritten_query=context.message,needs_context=bool(targets),reason='已校验输入协议的确定性投影')


def preference_proposal(context):
    turn = active_turn(context)
    values = {d.key:d.value for d in turn.directives if d.scope == 'persistent'
              and d.key in ('answer_length','question_frequency','example_density')} if turn else {}
    if not values:
        return None
    return {'label':'确认你的长期讲解偏好', 'reason':'你提出了长期偏好；确认后才保存，本轮回答已按本轮要求处理。',
            'values':values, 'default_scope':'long', 'origin':'explicit_request'}


def final_summary(context, result):
    turn = active_turn(context)
    if not turn:
        return None
    completed = result.get('answer_status') == 'answered'
    value=turn.model_dump()
    for frame in value['tasks']:
        done=completed
        if frame['action']=='resume_pending_question':
            done=done and bool(result.get('input_resume_question_id') or result.get('publication_mode')=='saved_formative_question')
        elif frame['action']=='submit_student_answer':
            done=done and (result.get('teaching') or {}).get('turn_move')=='answer'
        elif frame['action']=='propose_learning_plan':
            done=bool(result.get('session_plan') or result.get('q5_plan') or result.get('clarification',{}).get('mode')=='q5_session_plan')
        frame['state']='completed' if done else 'paused' if result.get('loop_paused') else 'pending'
    from models.input_understanding import GroundedTurn
    context.input_understanding=GroundedTurn.model_validate(value)
    return {'schema_version':turn.schema_version,'parser':turn.parser,'model_calls':turn.model_calls,
            'actions':[t.action for t in turn.tasks],
            'states':[t.state for t in context.input_understanding.tasks],
            'resolution_status':turn.resolution_status}
