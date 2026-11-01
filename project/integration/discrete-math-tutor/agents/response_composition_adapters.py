"""只投影已决定的任务和已核验正文；题目、评分与学习状态仍归原服务。"""
import hashlib
import json
import os

from agents.response_composition import plan_response
from models.learning_response import BlockSpec, LearningResponse, PublishedBlock, ResponsePlan


def response_plan(target_id, *, context=None, teaching=None, teaching_plan=None, execution=None):
    from agents.input_understanding.adapters import active_turn
    from agents.teaching_policy import canonical_strategy
    turn = active_turn(context) if context is not None else None
    strategy = getattr(teaching, 'strategy', None) or getattr(teaching_plan, 'strategy', 'direct')
    hint = bool(getattr(execution, 'hint_only', False) or getattr(teaching, 'limit_disclosure', False)
                or getattr(teaching_plan, 'action', None) == 'give_hint')
    if turn:
        hint = hint or any(set(t.constraints) & {'hint_only', 'no_full_answer'} for t in turn.tasks)
        hint = hint or any(d.key in ('hint_only', 'no_full_answer') and d.value is True
                          and d.scope != 'persistent' for d in turn.directives)
    canonical = strategy if strategy == 'prerequisite' else canonical_strategy(strategy)
    hint = hint or canonical == 'hint'
    strategy = {'self_explanation':'recap', 'direct_explanation':'direct'}.get(canonical, canonical)
    intents = getattr(execution, 'learning_intents', ())
    if not hint and 'example' in intents:
        strategy = 'worked_example'
    if not hint and 'summary' in intents:
        strategy = 'recap'
    plan = plan_response(target_id=target_id, strategy=strategy,
        tasks=['compare_content'] if 'compare' in intents else (), hint_only=hint)
    # 上游明确的内容动作优先于默认讲解策略；不从用户原话再次分类。
    content = {'explain_content':'explanation', 'compare_content':'comparison',
               'provide_hint':'hint', 'discuss_claim':'misconception'}
    frames = [t for t in turn.tasks if t.action in content] if turn else []
    if frames and not hint:
        specs, identities = [], {}
        for task in frames:
            key = f'b{len(specs)+1}'
            dependencies = [identities[d] for d in task.depends_on if d in identities]
            kind = content[task.action]
            if len(frames) == 1 and task.action == 'explain_content' and plan.blocks[0].semantic_type != 'direct_answer':
                kind = plan.blocks[0].semantic_type
            specs.append(BlockSpec(block_id=key, semantic_type=kind,
                depends_on=dependencies, task_frame_ids=[task.task_frame_id], target_ref=task.target_ref))
            identities[task.task_frame_id] = key
        # 样例/步骤来自既定教学策略，仍属于首项已确认内容任务。
        if len(specs) == 1 and frames[0].action == 'explain_content':
            for block in plan.blocks[1:]:
                specs.append(block.model_copy(update={'block_id':f'b{len(specs)+1}', 'depends_on':['b1'],
                    'task_frame_ids':specs[0].task_frame_ids, 'target_ref':specs[0].target_ref}))
        plan.blocks = specs
    elif frames:
        plan.blocks[0].task_frame_ids = [t.task_frame_id for t in frames]
    identity = json.dumps([target_id, strategy, [b.model_dump() for b in plan.blocks]], sort_keys=True)
    plan.plan_id = hashlib.sha256(identity.encode()).hexdigest()[:24]
    return ResponsePlan.model_validate(plan.model_dump())


def published_snapshot(*, reply, response_id, target_id, semantic_type='explanation', authority_ref=None):
    """调用方必须先完成原入口的核验；原样保存，不推断来源或把题目当作教材断言。"""
    if os.getenv('RESPONSE_COMPOSITION_ENABLED', '0') != '1' or not response_id or not reply.strip():
        return None
    plan = ResponsePlan(plan_id=hashlib.sha256(f'{target_id}:{semantic_type}'.encode()).hexdigest()[:24],
        target_id=target_id, strategy='host_snapshot',
        blocks=[BlockSpec(block_id='b1', semantic_type=semantic_type)])
    return LearningResponse(response_id=response_id, plan=plan, status='complete', reply=reply,
        blocks=[PublishedBlock(block_id='b1', semantic_type=semantic_type, rendered_text=reply,
            content_origin='host_snapshot', authority_ref=authority_ref or response_id)]).model_dump()


def snapshot_kind(*, teaching=None, teaching_plan=None, execution=None):
    if teaching is not None:
        if teaching.state.get('presentation'):
            return 'comparison' if teaching.state['presentation']['kind'] == 'concept_comparison' else 'procedure'
        if teaching.new_question or teaching.show_pending:
            return 'check_question'
        if teaching.state.get('assessment'):
            return 'feedback'
        if response_plan('snapshot', context=teaching.context, teaching=teaching).blocks[0].semantic_type == 'hint':
            return 'hint'
    if getattr(teaching_plan, 'action', None) == 'ask_question':
        return 'check_question'
    if getattr(execution, 'hint_only', False) or getattr(teaching_plan, 'action', None) == 'give_hint':
        return 'hint'
    return 'explanation'
