"""复用原生调度器及题目事务；复习操作只在学生明确选择后执行。"""
from copy import deepcopy
import hashlib
import math
import time

from deeptutor.learning.scheduler import RetentionScheduler, SpacedRepetitionScheduler
from deeptutor.learning.service import MasteryInteractionError
from .assessment_store import assessment_command, reviewed_question, review_action


def scheduler() -> RetentionScheduler:
    result = SpacedRepetitionScheduler()
    result.DEBUG_MODE = False  # 受管正式证据始终使用天；不消费上游秒级测试开关。
    return result


def evidence_identity(scope, path_id, event):
    value = [scope['student_id'], scope['course_id'], path_id, event.question_id,
             event.assessment_type, event.timestamp]
    return 'heart-' + hashlib.sha256(repr(value).encode()).hexdigest()[:32]


def sync_schedule(store, tx, objectives):
    engine = scheduler()
    for objective_id in objectives:
        events = [e for e in tx.progress.learning_evidence if e.knowledge_point_id == objective_id
                  and e.visual_context.get('verification') in ('reviewed_key', 'reviewed_rubric')]
        try:
            for event in events:
                item = tx.get_interaction(event.question_id)
                store._proof(tx.progress.book_id, item)
                if item.result.get('review_invalidated'):
                    raise MasteryInteractionError('assessment_voided')
        except MasteryInteractionError:
            continue  # 来源待核对时不把它当遗忘，也不缩短已保存的间隔。
        if events:
            kind = next((p.type for m in tx.progress.modules for p in m.knowledge_points if p.id == objective_id), None)
            if kind is None:
                continue
            tx.progress.knowledge_types[objective_id] = kind
            tx.progress.repetition_states[objective_id] = engine.replay(
                kind, events,
                desired_retention=tx.progress.desired_retention)
        else:
            tx.progress.repetition_states.pop(objective_id, None)
    projected = tx.progress.model_copy(deep=True)
    projected.learning_evidence = [e for e in projected.learning_evidence
        if e.visual_context.get('verification') in ('reviewed_key', 'reviewed_rubric')]
    tx.progress.review_queue = engine.build_review_queue(projected)
    tx.touch()


def validate_review_action(store, tx, value):
    origin = tx.get_interaction(value['origin'])
    store._proof(tx.progress.book_id, origin)
    if origin.result.get('review_invalidated'):
        raise MasteryInteractionError('assessment_voided')
    active = tx.active_interaction()
    state = origin.result.get('review_sessions', {}).get(value['review_id'], {})
    if value['action'] == 'start':
        if active is not None:
            raise MasteryInteractionError('review_path_busy')
        events = [e for e in tx.progress.learning_evidence if e.knowledge_point_id == origin.question.knowledge_point_id
                  and e.visual_context.get('verification') in ('reviewed_key', 'reviewed_rubric')]
        if not events or events[-1].evidence_id != value['evidence_id']:
            raise MasteryInteractionError('review_source_changed')
    if value['action'] in ('return', 'defer') and state.get('question_id') and active is not None:
        if active.interaction_id != state['question_id']:
            raise MasteryInteractionError('review_path_busy')
    if value['action'] == 'defer' and state.get('question_id'):
        child = tx.get_interaction(state['question_id'])
        if child is not None and child.status.value == 'graded':
            raise MasteryInteractionError('review_already_graded_finish_first')
    if value['action'] == 'finish':
        child = tx.get_interaction(state.get('question_id', ''))
        if child is None or child.status.value != 'graded' or child.result.get('review_invalidated'):
            raise MasteryInteractionError('review_ungraded')
        store._proof(tx.progress.book_id, child)
        if not any(e.question_id == child.interaction_id for e in tx.progress.learning_evidence):
            raise MasteryInteractionError('review_without_evidence')


def commit_review_action(tx, value):
    origin = tx.get_interaction(value['origin'])
    sessions = origin.result.setdefault('review_sessions', {})
    state = sessions.setdefault(value['review_id'], {})
    action = value['action']
    if action == 'start':
        state.update(question_id=value['question_id'], status='active', started_at=value['now'],
            return_position={'module_id': tx.progress.current_module_id, 'objective_index': tx.progress.current_kp_index})
        state.pop('deferred_until', None)
    elif action == 'defer':
        state.update(status='deferred', deferred_until=value['now'] + value['delay_hours'] * 3600)
    else:
        state.update(status='completed' if action == 'finish' else 'returned', updated_at=value['now'])
    tx.put_interaction(origin)
    tx.emit('review.' + action, {'review_id': value['review_id'], 'question_id': state.get('question_id'),
        'origin_question_id': value['origin']})


class NativeReviewService:
    def __init__(self, commands, *, clock=None):
        self.commands, self.store = commands, commands.store
        self.clock = clock or time.time

    def identity(self, path_id, event):
        scope = self.store._host_check
        key = event.visual_context.get('host_assessment', {}).get('key_version', '')
        value = [scope['student_id'], scope['course_id'], scope['session_id'], path_id,
                 event.evidence_id or evidence_identity(scope, path_id, event), event.question_id, key, event.result]
        return hashlib.sha256(repr(value).encode()).hexdigest()[:32]

    def queue(self, path_id):
        now = self.clock()
        if not math.isfinite(now):
            raise ValueError('invalid_review_clock')
        progress = self.store.load(path_id)
        projected = progress.model_copy(deep=True)
        projected.learning_evidence = [e for e in projected.learning_evidence
            if e.visual_context.get('verification') in ('reviewed_key', 'reviewed_rubric')]
        tasks = scheduler().build_review_queue(projected, now=now)
        names = {p.id: p.name for m in progress.modules for p in m.knowledge_points}
        rows = []
        for task in tasks:
            event = next((e for e in reversed(progress.learning_evidence)
                          if e.knowledge_point_id == task.knowledge_point_id and e.evidence_id == task.evidence_id), None)
            if event is None or event.visual_context.get('verification') not in ('reviewed_key', 'reviewed_rubric'):
                continue
            origin = self.commands._get(path_id, event.question_id)
            identity = self.identity(path_id, event)
            state = origin.result.get('review_sessions', {}).get(identity, {})
            link = origin.result.get('host_review')
            if link:
                parent = self.commands._get(path_id, link['origin'])
                episode = parent.result.get('review_sessions', {}).get(link['review_id'], {})
                if episode.get('status') == 'active':
                    identity, state = link['review_id'], episode
            try:
                self.store._proof(path_id, origin)
                valid = not origin.result.get('review_invalidated') and task.knowledge_point_id in names
            except MasteryInteractionError:
                valid = False
            until = state.get('deferred_until', 0)
            status = ('source_unavailable' if not valid else 'active' if state.get('status') == 'active' else
                      'deferred' if until > now else 'due' if task.due_at <= now else 'upcoming')
            reasons = ['间隔已到期' if task.due_at <= now else '按已保存证据安排后续复习']
            independent = event.visual_context.get('independent') is True
            if not independent:
                reasons.append('上次使用过帮助，可自行选择独立回忆')
            if event.result != 'correct':
                reasons.append('上次作答仍需巩固')
            hypotheses = origin.result.get('misconception_hypotheses', [])
            if any(h['status'] == 'hypothesis' for h in hypotheses):
                reasons.append('存在待核对的混淆假设，可选择概念辨析')
            if not valid:
                reasons = ['来源或审核状态已变化，待核对；不按遗忘处理']
            if status == 'active':
                child = self.commands._get(path_id, state['question_id'])
                actions = ['finish', 'return'] if child.status.value == 'graded' else ['return', 'defer']
            else:
                actions = ['start', 'defer']
            rows.append({'review_id': identity, 'objective_id': task.knowledge_point_id,
                'point': names.get(task.knowledge_point_id, task.knowledge_point_id),
                'status': status, 'due_at': task.due_at, 'deferred_until': until or None,
                'reason': '；'.join(reasons), 'evidence_id': event.evidence_id,
                'last_assessed_at': event.timestamp, 'independent': independent,
                'question_id': state.get('question_id'),
                'allowed_actions': actions if valid else [],
                'kind': 'scheduled_review'})
        return {'path_id': path_id, 'revision': progress.version, 'reviews': rows,
                'clock': now, 'timezone': 'Asia/Shanghai', 'changes_learning_mode': False}

    def act(self, path_id, *, review_id, action, command_id, base_revision, delay_hours=24):
        progress = self.store.load(path_id)
        event = next((e for e in reversed(progress.learning_evidence) if self.identity(path_id, e) == review_id), None)
        if event is None:
            raise MasteryInteractionError('review_not_found')
        origin = self.commands._get(path_id, event.question_id)
        proof = self.store._proof(path_id, origin)
        state = origin.result.get('review_sessions', {}).get(review_id, {})
        if action not in ('start', 'defer', 'finish', 'return') or delay_hours not in (1, 24, 72):
            raise MasteryInteractionError('invalid_review_action')
        now = self.clock()
        payload = {'review_id': review_id, 'action': action, 'delay_hours': delay_hours, 'base_revision': base_revision}
        value = dict(payload, origin=origin.interaction_id, evidence_id=event.evidence_id, now=now,
                     question_id='review-' + hashlib.sha256((review_id + command_id).encode()).hexdigest()[:40],
                     previous_question=state.get('question_id'))
        payload['question_id'] = value['question_id']
        from .learning_tool_adapter import current_learning_context
        context = current_learning_context()
        if action == 'start' and (context is None or self.store.path_id_for_session(context.session_id) != path_id):
            raise MasteryInteractionError('review_path_not_bound')
        receipt = origin.result.get('host_commands', {}).get(command_id)
        if action == 'start' and state.get('status') == 'active' and not receipt:
            raise MasteryInteractionError('review_already_started')
        with assessment_command(path_id, origin.interaction_id, command_id, 'review_' + action, payload), review_action(value):
            if action == 'start':
                question = origin.question.model_copy(deep=True, update={'question_id': value['question_id'], 'created_at': now})
                with reviewed_question(path_id, question, reviewer_id=proof['reviewer_id'], key_version=proof['key_version'],
                                       sources=proof['sources'], rubric=proof.get('rubric', [])):
                    _, child, _ = self.commands.service.register_question(path_id, question, session_id=context.session_id)
            else:
                active = self.store.get_active_interaction(path_id)
                if action in ('defer', 'return') and active is not None and active.interaction_id == state.get('question_id'):
                    self.commands.service.abandon_active_question(path_id)
                else:
                    self.store.mutate(path_id, lambda tx: None)
                child = self.store.get_interaction(path_id, state.get('question_id', '')) if state.get('question_id') else None
        result = self.queue(path_id)
        if child is not None:
            from .learning_cards import NativeLearningCards
            result.update(NativeLearningCards(self.commands).deck(path_id, child.interaction_id))
            result['question_id'] = child.interaction_id
        result['action'] = action
        return result
