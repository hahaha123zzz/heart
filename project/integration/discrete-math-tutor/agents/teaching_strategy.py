"""One bounded policy for TeachingTurn; execution stays in Q3/Q4/Q5.

Uses the existing 13-entry registry and the generation call as selector.
No learner-state store, extra model call, or tool permission is introduced.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from agents.teaching_policy import canonical_strategy, load_library, resolve_teaching_mode, forbids_full_answer

POLICY_VERSION = 'teaching-v2'


class TeachingMove(BaseModel):
    model_config = ConfigDict(extra='forbid')
    move_id: str
    action: str
    requires: list[str] = Field(default_factory=list)
    status: Literal['planned', 'published', 'not_observed'] = 'planned'


class TeachingStrategyPlan(BaseModel):
    model_config = ConfigDict(extra='forbid')
    decision_id: str
    policy_version: Literal['teaching-v2'] = POLICY_VERSION
    registry_version: str = '2.0'
    student_id: str
    session_id: str
    task_id: str
    task_revision: int | None = None
    target_ref: str
    primary_strategy: str
    candidates: list[str] = Field(min_length=1, max_length=13)
    moves: list[TeachingMove] = Field(max_length=6)
    depth: Literal['brief', 'normal', 'stepwise'] = 'normal'
    interaction_boundary: Literal['close', 'wait_for_student', 'preserve_pending']
    allow_check: bool = False
    stop_conditions: list[str]
    evidence_mode: Literal['blended', 'textbook']
    fallback: str = 'direct_explanation'
    decision_summary: list[str] = Field(max_length=8)
    status: Literal['planned', 'prepared', 'published', 'waiting'] = 'planned'
    reported_strategy: str | None = None
    publication_receipt: str | None = None
    source_ids: list[str] = Field(default_factory=list, max_length=8)
    tool_receipts: list[dict] = Field(default_factory=list, max_length=24)
    evidence_recovery: Literal['not_needed', 'attempted', 'recovered', 'blocked'] = 'not_needed'

    @model_validator(mode='after')
    def valid_registry_and_moves(self):
        known = {s['id'] for s in load_library()}
        if not set(self.candidates) <= known or self.primary_strategy not in self.candidates or self.fallback not in known:
            raise ValueError('invalid_strategy_candidates')
        if len(set(self.candidates)) != len(self.candidates):
            raise ValueError('duplicate_strategy_candidates')
        if len({m.move_id for m in self.moves}) != len(self.moves):
            raise ValueError('duplicate_teaching_move')
        return self


def runtime_strategy(strategy):
    # Compatibility projection only; strategy_id retains distinctions lost here.
    return {'direct_explanation':'explain', 'conceptual_comparison':'contrast',
            'scaffolding':'break_down', 'socratic_questioning':'guided_practice',
            'guided_revision':'feedback', 'direct_correction':'feedback',
            'counterexample':'worked_example', 'self_explanation':'guided_practice',
            'retrieval_practice':'guided_practice', 'summary':'explain'}.get(strategy, strategy)


def configure_moves(plan, strategy):
    entry = next(s for s in load_library() if s['id'] == strategy)
    actions = list(entry['moves'])
    if plan.interaction_boundary != 'wait_for_student':
        actions = [a for a in actions if a != 'ask_check']
    if plan.evidence_mode == 'textbook':
        actions.insert(0, 'read_material')
    plan.moves = [TeachingMove(move_id=f'{plan.decision_id}:{i}', action=a,
                              requires=list(entry.get('requires', []))) for i,a in enumerate(actions)]
    plan.primary_strategy = strategy


@dataclass(frozen=True)
class StrategyInputs:
    student_id: str
    session_id: str
    request_id: str
    task_id: str
    task_revision: int | None
    target_ref: str
    message: str
    mode: str
    move: str
    difficulty: bool
    skip: bool
    constraints: frozenset[str]
    allow_check: bool
    invite_check: bool
    has_pending: bool
    interjection: bool
    assessment: dict
    question_frequency: float
    difficulty_locus: str | None
    previous_strategy: str
    evidence_mode: str
    route_kind: str = ''
    scope: str = ''


def _previous_strategy(old,target_ref):
    previous=old.get('strategy_plan') or {}
    if previous:
        return previous.get('primary_strategy','') if previous.get('target_ref')==target_ref else ''
    if old.get('target_id') and old['target_id']!=target_ref: return ''
    return canonical_strategy(old.get('last_strategy',''))


def decide(turn, old):
    constraints = {c for t in turn.input_turn.tasks for c in t.constraints} if turn.input_turn else set()
    constraints.update(getattr(turn,'extra_strategy_constraints',()))
    request=turn.request
    route=turn.turn_route
    return _decide(StrategyInputs(student_id=request.student_id,session_id=request.session_id,
        request_id=request.request_id or '',task_id=request.task_id or '',task_revision=request.task_revision,
        target_ref=turn.state.get('target_id') or turn.objective.id,message=request.message,mode=turn.teaching_mode,
        move=turn.strategy_decision.move,difficulty=turn.difficulty,skip=turn.skip,constraints=frozenset(constraints),
        allow_check=turn.state['allow_check'],invite_check=turn.strategy_decision.invite_check,
        has_pending=bool(turn.progress.pending_question),interjection=turn.interjection,
        assessment=turn.state.get('assessment') or {},question_frequency=turn.context.preferences.get('question_frequency',.5),
        difficulty_locus=turn._locus() if turn.six_dim and os.getenv('LABELS_POLICY','0')=='1' else None,
        previous_strategy=_previous_strategy(old,turn.state.get('target_id') or turn.objective.id),evidence_mode=turn.evidence_mode,
        route_kind=route.kind if route else '',scope=route.scope if route else ''))


def decide_for_context(context, execution, *, assessment=None):
    """Legacy/selection/exercise adapter; reads the same protocol without grading or storing state."""
    from agents.adaptive_tutoring import analyze_teaching_turn, is_difficulty, NO_QUIZ, SKIP_CHECK
    from agents.input_understanding.adapters import active_turn
    preferences={**context.preferences,**execution.preferences}
    pending=bool((context.tutoring.get('progress') or {}).get('pending_question'))
    features=analyze_teaching_turn(context.message,has_pending=pending,
        question_frequency=preferences.get('question_frequency',.5))
    input_turn=active_turn(context)
    constraints=set(execution.answer_constraints)
    if input_turn: constraints.update(c for t in input_turn.tasks for c in t.constraints)
    if execution.hint_only and execution.teaching_mode!='practice': constraints.update(('hint_only','no_full_answer'))
    no_questions=execution.no_questions or bool(NO_QUIZ.search(context.message)) or (
        ((context.session_study_plan or {}).get('request') or {}).get('practice_preference')=='none'
    )
    locus=None
    if input_turn and os.getenv('LABELS_POLICY','0')=='1':
        from agents.input_understanding import ontology
        locus=(ontology.build(input_turn,context)['learner_state']['difficulty_locus'] or {}).get('value')
    header=input_turn.context if input_turn else None
    target=(execution.target_refs[0] if execution.target_refs else
        (context.activity_target or {}).get('target_id') or context.knowledge_point or 'current-goal')
    route=context.turn_route or {}
    return _decide(StrategyInputs(student_id=context.student_id,session_id=context.session_id,
        request_id=context.request_id or '',task_id=context.task_id or (header.task_id if header else '') or '',
        task_revision=context.task_revision or (header.task_revision if header else None),
        target_ref=target,message=context.message,
        mode=execution.teaching_mode if execution.teaching_mode!='auto' else resolve_teaching_mode(context.message),
        move=features.move,difficulty=is_difficulty(context.message),skip=bool(SKIP_CHECK.fullmatch(context.message.strip())),
        constraints=frozenset(constraints),allow_check=not no_questions,invite_check=features.invite_check,
        has_pending=pending,interjection=False,assessment=assessment or {},
        question_frequency=preferences.get('question_frequency',.5),difficulty_locus=locus,
        previous_strategy=_previous_strategy(context.tutoring,target),evidence_mode=features.evidence_mode,
        route_kind=route.get('kind',''),scope=route.get('scope','')))


def strategy_action(plan):
    if plan.interaction_boundary=='wait_for_student': return 'ask_question'
    return {'hint':'give_hint','scaffolding':'give_hint','guided_revision':'give_hint',
            'worked_example':'give_example','counterexample':'give_example','summary':'summarize'}.get(plan.primary_strategy,'explain')


def align_legacy_plan(strategy, plan, move=None):
    plan.strategy=strategy.primary_strategy
    plan.action=strategy_action(strategy)
    plan.rationale='; '.join(strategy.decision_summary)
    if move is not None:
        move.instructional_move=strategy.primary_strategy
        move.action=plan.action
        move.rationale=plan.rationale


def public_plan(plan):
    return plan.model_dump(mode='json',exclude={'student_id','session_id'})


def publish_external_strategy(context, plan, answer_text, *, source_ids=()):
    """A host publication receipt, never a claim of semantic execution or mastery."""
    if not answer_text.strip(): raise ValueError('empty_strategy_publication')
    if not plan.publication_receipt:
        plan.publication_receipt=plan.decision_id+':publication'
        plan.status='published'
        plan.source_ids=[str(s) for s in source_ids][:8]
        for move in plan.moves: move.status='not_observed'
    state=context.tutoring
    state['strategy_plan']=plan.model_dump(mode='json')
    history=state.setdefault('strategy_history',[])
    if not any(r.get('decision_id')==plan.decision_id for r in history):
        from agents.adaptive_tutoring import is_difficulty
        previous=next((r for r in reversed(history) if r.get('target_ref')==plan.target_ref),None)
        if previous is not None and is_difficulty(context.message):
            previous['feedback']=(previous.get('feedback',[])+[{'feedback_id':plan.decision_id,
                'difficulty_reported':True,'verdict':None,'verification':'self_report','causal_effect':False}])[-8:]
        history.append({'decision_id':plan.decision_id,'target_ref':plan.target_ref,
            'selected_strategy':plan.primary_strategy,'reported_strategy':None,
            'publication_receipt':plan.publication_receipt,'answer_sha256':hashlib.sha256(answer_text.encode()).hexdigest(),
            'source_ids':list(plan.source_ids),'feedback':[]})
        state['strategy_history']=history[-20:]
        state['used_strategies']=(list(state.get('used_strategies') or [])+[runtime_strategy(plan.primary_strategy)])[-6:]
    if state.get('schema') and state.get('target_id') and state['target_id']!=plan.target_ref:
        return public_plan(plan)
    state['last_strategy']=runtime_strategy(plan.primary_strategy)
    state['last_summary']=re.sub(r'\s+',' ',answer_text).strip()[:350]
    return public_plan(plan)



def _decide(inputs):
    """Rules filter, context ranks; the existing teaching_step may select within candidates."""
    text = inputs.message
    constraints = set(inputs.constraints)
    if forbids_full_answer(text):
        constraints.add('no_full_answer')
    hint_only = ('hint_only' in constraints or 'no_full_answer' in constraints and inputs.mode!='practice') or (
        inputs.mode == 'guided' and not inputs.invite_check)
    allow = bool(inputs.allow_check and inputs.invite_check
                 and not inputs.interjection and not inputs.has_pending
                 and not constraints & {'no_questions','verdict_only'})
    assessment = inputs.assessment
    verdict = assessment.get('verdict')
    if (verdict and inputs.mode == 'auto' and inputs.allow_check
            and inputs.question_frequency >= .85
            and not inputs.interjection and not constraints & {'no_questions','verdict_only'}):
        allow = True
    locus = inputs.difficulty_locus
    reasons = ['constraints_before_labels', 'formal_mastery_unchanged']
    if hint_only:
        preferred = ['hint','scaffolding']; reasons.append('explicit_disclosure_limit')
    elif 'example_before_proof' in constraints:
        preferred = ['worked_example','direct_explanation']; reasons.append('explicit_example_before_proof')
    elif inputs.mode == 'direct':
        preferred = ['direct_explanation','worked_example']; reasons.append('explicit_direct_request')
    elif inputs.skip:
        preferred = ['summary']; reasons.append('student_skipped')
    elif inputs.route_kind == 'comparison':
        preferred = ['conceptual_comparison','worked_example','scaffolding']; reasons.append('turn_route:comparison')
    elif inputs.route_kind == 'hint':
        preferred = ['hint','scaffolding']; reasons.append('turn_route:hint')
    elif inputs.route_kind == 'exercise' and verdict is None:
        preferred = (['retrieval_practice','socratic_questioning'] if allow
                     else ['worked_example','scaffolding']); reasons.append('turn_route:exercise')
    elif inputs.mode == 'practice' and allow:
        preferred = ['retrieval_practice','socratic_questioning']
    elif verdict == 'partial':
        preferred = ['guided_revision','conceptual_comparison']
    elif verdict == 'incorrect':
        preferred = ['direct_correction','counterexample','worked_example']
    elif verdict == 'correct':
        preferred = ['transfer','self_explanation','summary'] if allow else ['summary','direct_explanation']
    elif inputs.mode == 'review':
        preferred = ['summary','conceptual_comparison','direct_explanation']
    elif locus == 'discrimination' or re.search(r'分不清|区别|对比|比较|混淆', text):
        preferred = ['conceptual_comparison','worked_example','scaffolding']
    elif locus in ('pace','procedure') or re.search(r'太快|跟不上|步骤|怎么做|如何操作', text):
        preferred = ['scaffolding','worked_example','hint']
    elif locus == 'memory' or re.search(r'记不住|想不起来', text):
        preferred = ['retrieval_practice','worked_example','scaffolding'] if allow else ['worked_example','scaffolding']
    elif re.search(r'总结|概括|归纳', text):
        preferred = ['summary','direct_explanation']
    elif inputs.difficulty or inputs.move == 'teach_with_example':
        preferred = ['worked_example','scaffolding','direct_explanation']
    elif inputs.mode == 'guided':
        preferred = ['socratic_questioning','hint','worked_example']
    else:
        preferred = ['direct_explanation','worked_example','scaffolding']
    if locus: reasons.append('difficulty_locus:' + locus)
    if verdict: reasons.append('provisional_response:' + verdict)
    library = load_library()
    available = []
    for item in library:
        sid = item['id']
        requirements = set(item.get('requires', []))
        if 'student_response' in requirements and not verdict: continue
        if sid == 'guided_revision' and verdict != 'partial': continue
        if sid in ('direct_correction','counterexample') and verdict != 'incorrect': continue
        if 'allow_interaction' in requirements and not allow: continue
        if hint_only and sid not in ('hint','scaffolding'): continue
        if inputs.mode == 'direct' and sid not in ('direct_explanation','worked_example','conceptual_comparison','summary'): continue
        available.append(sid)
    candidates = [s for s in preferred if s in available]
    if not candidates:
        candidates = ['hint' if hint_only else 'direct_explanation']
    # Only reduce repetition after explicit difficulty, never a blanket rotation.
    previous = inputs.previous_strategy
    if inputs.difficulty and 'example_before_proof' not in constraints and len(candidates)>1 and candidates[0] == previous:
        candidates = candidates[1:] + candidates[:1]
        reasons.append('previous_published_method_did_not_resolve_reported_difficulty')
    identity = [inputs.student_id, inputs.session_id, inputs.task_id or inputs.request_id,
                inputs.task_revision, inputs.target_ref]
    decision_id = hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:24]
    plan = TeachingStrategyPlan(decision_id=decision_id, student_id=inputs.student_id,
        session_id=inputs.session_id, task_id=inputs.task_id or inputs.request_id,
        task_revision=inputs.task_revision, target_ref=str(identity[-1]), primary_strategy=candidates[0],
        candidates=candidates, moves=[], allow_check=bool(inputs.allow_check and inputs.mode != 'direct' and not hint_only
            and not constraints & {'no_questions','verdict_only'}), depth='stepwise' if inputs.difficulty or hint_only else 'normal',
        interaction_boundary='wait_for_student' if allow else 'preserve_pending' if inputs.has_pending else 'close',
        stop_conditions=['wait_for_student' if allow else 'published_current_goal', 'student_skip', 'task_cancelled_or_stale'],
        evidence_mode=inputs.evidence_mode, fallback='hint' if hint_only else 'direct_explanation', decision_summary=reasons)
    configure_moves(plan, plan.primary_strategy)
    return plan


def strategy_prompt(plan, *, selector_tool=True):
    library = {s['id']:s for s in load_library()}
    fragments = [{'strategy_id':s, 'strategy':runtime_strategy(s), 'instruction':library[s]['render_hint']} for s in plan.candidates[:3]]
    payload = plan.model_dump(exclude={'student_id','session_id','tool_receipts'})
    return ('\n统一教学决策（约束优先于策略片段；动作只是计划，不能宣称已完成）：'
        + json.dumps(payload,ensure_ascii=False) + '\n按需策略片段：' + json.dumps(fragments,ensure_ascii=False)
        + ('\n按有序 moves 回应当前目标。复杂情境可在现有 teaching_step 调用中用 strategy_id 选择候选；'
           '不得选择候选外策略。工具 strategy 仍用兼容名称。' if selector_tool else
           '\n按已选策略的有序 moves 回应当前目标；仅使用此入口已有的获准工具。')
        + '只给提示时不披露完整答案。'
        'ask_check 必须登记原问题并停止；close 不主动出题。没有发布回执不能报告执行成功。')
