"""服务端执行边界；模型理解结果不能签发写入授权。"""
from models.input_understanding import ExecutionDecision


READ_ACTIONS = {'explain_content', 'compare_content', 'provide_hint', 'discuss_claim',
                'resume_pending_question', 'resume_learning_activity', 'clarify_reference'}


def decide(turn):
    if 'mixed_state_changes' in turn.unresolved:
        return ExecutionDecision(status='reject',reason='mixed_commands_require_confirmation')
    refs = {r.ref_id: r for r in turn.references}
    actions = [t.action for t in turn.tasks]
    targets = [refs[t.target_ref] for t in turn.tasks if t.target_ref]
    if any(r.status in ('unauthorized', 'stale') for r in targets):
        return ExecutionDecision(status='reject', reason='reference_stale_or_unauthorized')
    if any(r.status in ('missing', 'ambiguous', 'partial') for r in targets):
        return ExecutionDecision(status='clarify', reason='reference_required')
    if turn.resolution_status == 'ambiguous':
        return ExecutionDecision(status='clarify', reason='meaning_required')
    if any(t.action not in READ_ACTIONS for t in turn.tasks):
        if turn.parser != 'rule' or len(turn.tasks) != 1:
            return ExecutionDecision(status='reject', reason='mixed_commands_require_confirmation')
        return ExecutionDecision(status='approved', actions=actions, reason='existing_service_must_authorize')
    return ExecutionDecision(status='read_only', actions=actions)


def clarification_result(turn, context):
    unresolved = next((r for r in turn.references if r.status in ('missing', 'ambiguous', 'partial')), None)
    candidates = set(unresolved.candidate_ids if unresolved else ())
    options = [{'id': r.canonical_id, 'label': r.title[:140]} for r in context.reference_objects
               if r.canonical_id in candidates][:4]
    question = ('你指的是哪个已保存的片段？' if options else
                '请提供图号或重新圈选教材中的图。' if unresolved and unresolved.kind == 'figure' else
                '请补充你指的例子或具体内容，也可以重新圈选教材。' if unresolved else
                '请补充要处理的具体对象或步骤，我会接着完成原请求。')
    return {'answer_status': 'awaiting_clarification', 'reply': question, 'step_advanced': False,
            'loop_paused': True, 'clarification': {'mode': 'input_reference', 'question': question,
                'missing_slots': ['target'], 'options': options}}


def selected_reference(previous, request):
    import re
    options = (previous.get('result', {}).get('clarification') or {}).get('options') or []
    if request.selected_option:
        return request.selected_option
    match = re.fullmatch(r'第?([一二三四1234])个[。！!]?\s*', request.message.strip())
    if match:
        index = '一二三四'.find(match[1]) if match[1] in '一二三四' else int(match[1])-1
        if index < len(options):
            return options[index]['id']
    return None
