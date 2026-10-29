"""原生测评事务的宿主门禁；沿用上游题目、评分、事件和存储。"""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
import hashlib
import hmac
import json
import os

from deeptutor.learning.service import LearningService, MasteryInteractionError
from .learning_write_guard import HostAuthorizedLearningStore

_review = ContextVar('heart_reviewed_question', default=None)
_decision = ContextVar('heart_assessment_decision', default=None)
_repair = ContextVar('heart_assessment_repair', default=None)
_command = ContextVar('heart_assessment_command', default=None)
_review_action = ContextVar('heart_review_action', default=None)


@contextmanager
def review_action(value):
    token = _review_action.set(deepcopy(value))
    try:
        yield
    finally:
        _review_action.reset(token)


@contextmanager
def reviewed_question(path_id, question, *, reviewer_id, key_version, sources, rubric=()):
    """仅供可信宿主审核流程调用；不注册为工具或浏览器参数。"""
    if not reviewer_id.strip() or not key_version.strip() or not sources:
        raise MasteryInteractionError('question_review_required')
    if not question.prompt.strip() or len(question.prompt) > 2000 or len(question.expected_answer) > 4000:
        raise MasteryInteractionError('assessment_question_invalid')
    token = _review.set({'path_id': path_id, 'question': question.model_dump(mode='json'),
                         'reviewer_id': reviewer_id, 'key_version': key_version,
                         'sources': deepcopy(sources), 'rubric': deepcopy(list(rubric))})
    try:
        yield
    finally:
        _review.reset(token)


@contextmanager
def reviewed_decision(value):
    token = _decision.set(deepcopy(value))
    try:
        yield
    finally:
        _decision.reset(token)


@contextmanager
def assessment_command(path_id, question_id, command_id, action, payload):
    secret = os.getenv('DEEPTUTOR_BRIDGE_TOKEN', '')
    if len(secret) < 32 or not command_id:
        raise MasteryInteractionError('assessment_command_required')
    signature = hmac.new(secret.encode(), json.dumps([action, payload], ensure_ascii=False,
        sort_keys=True, separators=(',', ':')).encode(), hashlib.sha256).hexdigest()
    token = _command.set({'path_id': path_id, 'question_id': question_id,
                          'command_id': command_id, 'action': action, 'signature': signature,
                          'confidence': payload.get('confidence'), 'base_revision': payload.get('base_revision'),
                          'payload': deepcopy(payload)})
    try:
        yield
    finally:
        _command.reset(token)


def assistance(interaction):
    events = interaction.result.get('assistance_events', [])
    return {'hints_used': sum(e['kind'] == 'hint' for e in events),
            'max_hint_level': max((e.get('level', 0) for e in events), default=0),
            'examples_used': sum(e['kind'] == 'example' for e in events),
            'explanations_used': sum(e['kind'] == 'explanation' for e in events),
            'full_explanation_seen': any(e.get('full_explanation') for e in events),
            'events': deepcopy(events)}


class HostAssessmentStore(HostAuthorizedLearningStore):
    def _authorize(self):
        self._host_backend.authorize_native_assessment(self._host_check)

    def _seal(self, path_id, question, proof):
        secret = os.getenv('DEEPTUTOR_BRIDGE_TOKEN', '')
        if len(secret) < 32:
            raise MasteryInteractionError('assessment_authority_unavailable')
        scope = {k: self._host_check[k] for k in ('student_id', 'course_id', 'session_id', 'memory_epoch', 'material_versions')}
        payload = {'domain': 'heart-assessment-v1', 'scope': scope, 'path_id': path_id,
                   'question': question.model_dump(mode='json'),
                   'reviewer_id': proof['reviewer_id'], 'key_version': proof['key_version'],
                   'sources': proof['sources'], 'rubric': proof.get('rubric', [])}
        if 'card_support' in proof:
            payload['card_support'] = proof['card_support']
        return hmac.new(secret.encode(), json.dumps(payload, sort_keys=True, ensure_ascii=False,
                        separators=(',', ':')).encode(), hashlib.sha256).hexdigest()

    def _sources(self, sources):
        from agents.adaptive_tutoring import verified_sources
        if not sources or len(sources) > 8:
            raise MasteryInteractionError('assessment_source_unavailable')
        if any(self._host_check['material_versions'].get(s.get('document_id')) != s.get('version') for s in sources):
            raise MasteryInteractionError('assessment_source_changed')
        try:
            verified = verified_sources(sources)
        except (OSError, ValueError, KeyError) as exc:
            raise MasteryInteractionError('assessment_source_unavailable') from exc
        if len(verified) != len(sources):
            raise MasteryInteractionError('assessment_source_unavailable')

    def _proof(self, path_id, interaction):
        proof = interaction.result.get('host_assessment') or {}
        if not all(proof.get(k) for k in ('reviewer_id', 'key_version', 'sources', 'seal')):
            raise MasteryInteractionError('question_review_required')
        if not hmac.compare_digest(proof['seal'], self._seal(path_id, interaction.question, proof)):
            raise MasteryInteractionError('assessment_question_changed')
        self._sources(proof['sources'])
        return proof

    def mutate(self, book_id, fn, **kwargs):
        def guarded(tx):
            before = tx.active_interaction()
            initial_active = before
            review = _review_action.get()
            command = _command.get()
            if command and command['path_id'] == book_id:
                before = tx.get_interaction(command['question_id'])
                if before is None:
                    raise MasteryInteractionError('question_not_found')
                receipt = before.result.get('host_commands', {}).get(command['command_id'])
                if receipt:
                    if receipt != command['signature']:
                        raise MasteryInteractionError('assessment_command_conflict')
                    action = command['action']
                    if action == 'review_start':
                        return (tx.get_interaction(command['payload']['question_id']), False)
                    return ((before, True) if action == 'grade' else False if action == 'skip'
                            else {} if action in ('defer', 'void', 'correct') else None if action == 'review' else before)
                if command.get('base_revision') is not None and tx.progress.version != command['base_revision']:
                    raise MasteryInteractionError('card_revision_conflict')
                if command['action'] in ('skip', 'defer', 'answer', 'help', 'present'):
                    active = tx.active_interaction()
                    if active is None or active.interaction_id != before.interaction_id:
                        raise MasteryInteractionError('stale_question')
            if review:
                from .review import validate_review_action
                validate_review_action(self, tx, review)
            repair = _repair.get()
            if repair and repair['path_id'] == book_id:
                before = tx.get_interaction(repair['question_id'])
            qualitative = deepcopy(tx.progress.qualitative_mastery)
            levels = deepcopy(tx.progress.mastery_levels)
            reviewed_at = max((e.timestamp for e in tx.progress.learning_evidence
                               if before is not None and e.question_id == before.interaction_id
                               and e.assessment_type == 'qualitative'), default=0)
            from .review import evidence_identity
            for event in tx.progress.learning_evidence:
                if not event.evidence_id and event.question_id:
                    event.evidence_id = evidence_identity(self._host_check, book_id, event)
                    tx.touch()
            old_evidence = {e.evidence_id for e in tx.progress.learning_evidence}
            result = fn(tx)
            for event in tx.progress.learning_evidence:
                if not event.evidence_id and event.question_id:
                    event.evidence_id = evidence_identity(self._host_check, book_id, event)
                    tx.touch()
            if (isinstance(result, tuple) and result and getattr(result[0], 'result', {}).get('review_invalidated')):
                raise MasteryInteractionError('assessment_voided')
            qualitative_changed = any(k not in qualitative or qualitative[k] != value
                   for k, value in tx.progress.qualitative_mastery.items()) or any(
                    e.assessment_type == 'qualitative' and e.evidence_id not in old_evidence
                    for e in tx.progress.learning_evidence)
            decision = _decision.get()
            if qualitative_changed:
                if (before is None or before.status.value != 'answered' or not decision
                        or decision['question_id'] != before.interaction_id
                        or decision['answer'] != before.user_answer
                        or not decision['reviewer_id'] or not decision['criteria']):
                    raise MasteryInteractionError('qualitative_rubric_review_required')
                proof = self._proof(book_id, before)
                required = {c['id'] for c in proof.get('rubric', [])}
                if not required or required != set(decision['criteria']):
                    raise MasteryInteractionError('rubric_changed')
                kp_id = before.question.knowledge_point_id
                passed = all(v == 'met' for v in decision['criteria'].values())
                if tx.progress.qualitative_mastery.get(kp_id) != passed:
                    raise MasteryInteractionError('rubric_result_changed')
                before.result['review'] = deepcopy(decision)
                before.result['review_status'] = 'graded'
                before.result['assessment_version'] = 'native-rubric-reviewed-v1'
                before.result['mastery_before_review'] = {'qualitative': qualitative.get(kp_id), 'level': levels.get(kp_id)}
                before.status = type(before.status).GRADED
                before.result['is_correct'] = passed
                if assistance(before)['events'] or self._teaching_after(tx, before):
                    tx.progress.qualitative_mastery = qualitative
                    tx.progress.mastery_levels = levels
                for event in tx.progress.learning_evidence:
                    if event.evidence_id not in old_evidence and event.knowledge_point_id == kp_id:
                        event.question_id = before.interaction_id
                        event.visual_context.update(host_assessment=deepcopy(proof),
                            verification='reviewed_rubric', assessment_version='native-rubric-reviewed-v1')
                        event.confidence = before.result.get('self_confidence')
                        self._assistance(tx, before, event)
                tx.progress.pending_question = None
                tx.put_interaction(before)
                tx.emit('interaction.graded', {'interaction_id': before.interaction_id, 'verification': 'reviewed_rubric'})
            active = tx.active_interaction()
            if initial_active is None and active is not None:
                approval = _review.get()
                question = active.question
                if (not approval or approval['path_id'] != book_id
                        or approval['question'] != question.model_dump(mode='json')):
                    raise MasteryInteractionError('question_review_required')
                objective = next((p for m in tx.progress.modules for p in m.knowledge_points
                                  if p.id == question.knowledge_point_id), None)
                quantitative = objective is not None and objective.type.value in ('memory', 'procedure')
                from deeptutor.capabilities.mastery.tools import _normalize_quiz_contract
                try:
                    _normalize_quiz_contract(question.question_type,
                        [o.model_dump() for o in question.options], question.expected_answer)
                except ValueError as exc:
                    raise MasteryInteractionError('assessment_question_invalid') from exc
                valid = (question.question_type == 'choice' and question.expected_answer in question.choice_map
                         and len(question.options) >= 2) if quantitative else (
                         question.question_type == 'open' and bool(approval['rubric']) and bool(question.expected_answer.strip()))
                if objective is None or not valid or question.visual_context:
                    raise MasteryInteractionError('assessment_type_requires_review')
                self._sources(approval['sources'])
                proof = {k: deepcopy(approval[k]) for k in ('reviewer_id', 'key_version', 'sources', 'rubric')}
                if review and review['action'] == 'start':
                    origin = tx.get_interaction(review['origin'])
                    support = origin.result['host_assessment'].get('card_support')
                    if support:
                        proof['card_support'] = deepcopy(support)
                proof['seal'] = self._seal(book_id, question, proof)
                active.result['host_assessment'] = proof
                if review and review['action'] == 'start':
                    active.result['host_review'] = {k: review[k] for k in ('origin', 'review_id')}
                    if review.get('previous_question'):
                        previous = tx.get_interaction(review['previous_question'])
                        active.result['assistance_events'] = deepcopy(previous.result.get('assistance_events', []))
                tx.put_interaction(active)
            if before is not None:
                after = tx.get_interaction(before.interaction_id)
                if repair and repair['action'] == 'void':
                    after.result.update({k: deepcopy(v) for k, v in before.result.items()
                                         if k in ('host_assessment', 'assistance_events', 'self_confidence', 'host_commands', 'assessment_version')})
                    after.result['review_invalidated'] = True
                    after.result['is_correct'] = None
                    tx.put_interaction(after)
                if repair and repair['action'] == 'correct':
                    approval = _review.get()
                    if (not approval or approval['path_id'] != book_id
                            or approval['question'] != after.question.model_dump(mode='json')):
                        raise MasteryInteractionError('question_review_required')
                    self._sources(approval['sources'])
                    proof = {k: deepcopy(approval[k]) for k in ('reviewer_id', 'key_version', 'sources', 'rubric')}
                    proof['seal'] = self._seal(book_id, after.question, proof)
                    after.result['host_assessment'] = proof
                    after.result.pop('review_invalidated', None)
                    after.result['misconception_hypotheses'] = [dict(h, status='dismissed')
                        for h in before.result.get('misconception_hypotheses', [])]
                    after.result.update({k: deepcopy(v) for k, v in before.result.items()
                                         if k in ('assistance_events', 'self_confidence', 'host_commands', 'published_help', 'card_requests', 'card_commands', 'card_view', 'card_explanation_requested', 'card_return_path', 'host_review')})
                    # 修订答案键后旧讲解不再作为可发布帮助，等待新的审核内容。
                    after.result.pop('published_help', None)
                    after.result.pop('card_explanation_requested', None)
                    # 修订答案键后旧讲解不再作为可发布帮助，等待新的审核内容。
                    after.result.pop('published_help', None)
                    after.result.pop('card_explanation_requested', None)
                    for event in tx.progress.learning_evidence:
                        if event.question_id == before.interaction_id:
                            event.visual_context['host_assessment'] = deepcopy(proof)
                            self._assistance(tx, before, event)
                    tx.put_interaction(after)
                if repair and repair['action'] == 'void' and before.result.get('review'):
                    kp_id = before.question.knowledge_point_id
                    if any(e.knowledge_point_id == kp_id and e.assessment_type == 'qualitative'
                           and e.question_id != before.interaction_id and e.timestamp > reviewed_at
                           for e in tx.progress.learning_evidence):
                        raise MasteryInteractionError('later_assessment_requires_review')
                    tx.progress.learning_evidence = [e for e in tx.progress.learning_evidence
                                                    if e.question_id != before.interaction_id]
                    snapshot = before.result['mastery_before_review']
                    for values, name in ((tx.progress.qualitative_mastery, 'qualitative'),
                                         (tx.progress.mastery_levels, 'level')):
                        if snapshot[name] is None:
                            values.pop(kp_id, None)
                        else:
                            values[kp_id] = snapshot[name]
                    after.result['review_invalidated'] = True
                    after.result['is_correct'] = None
                    after.result['misconception_hypotheses'] = [dict(h, status='dismissed')
                        for h in before.result.get('misconception_hypotheses', [])]
                    tx.put_interaction(after)
                if after.status.value == 'answered' and before.status.value in ('registered', 'awaiting_input'):
                    self._proof(book_id, before)
                    from deeptutor.learning.pending import is_readable_choice_answer
                    if before.question.question_type == 'choice' and not is_readable_choice_answer(after.user_answer, before.question.choice_map):
                        raise MasteryInteractionError('answer_needs_clarification')
                if after.status.value == 'graded' and before.status.value != 'graded':
                    if before.question.question_type != 'choice':
                        raise MasteryInteractionError('qualitative_rubric_review_required')
                    proof = self._proof(book_id, before)
                    if before.status.value != 'answered':
                        raise MasteryInteractionError('student_answer_not_recorded')
                    from deeptutor.learning.grading import grade_answer
                    from deeptutor.learning.pending import resolve_choice_submission
                    submitted = resolve_choice_submission(before.user_answer, before.question.choice_map) or before.user_answer
                    expected = grade_answer(submitted, before.question.expected_answer, before.question.question_type)
                    if after.user_answer != before.user_answer or after.result.get('is_correct') != expected:
                        raise MasteryInteractionError('assessment_answer_changed')
                    after.result['host_assessment'] = proof
                    after.result['assessment_version'] = 'native-choice-reviewed-v1'
                    after.result.update({k: deepcopy(v) for k, v in before.result.items()
                                         if k in ('assistance_events', 'self_confidence', 'host_commands', 'published_help', 'card_requests', 'card_commands', 'card_view', 'card_explanation_requested', 'card_return_path', 'host_review')})
                    tx.put_interaction(after)
                    for event in tx.progress.learning_evidence:
                        if event.question_id == before.interaction_id:
                            event.visual_context['host_assessment'] = deepcopy(proof)
                            event.visual_context['verification'] = 'reviewed_key'
                            event.visual_context['assessment_version'] = 'native-choice-reviewed-v1'
                            event.confidence = before.result.get('self_confidence')
                            self._assistance(tx, before, event)
                    if assistance(before)['events'] or self._teaching_after(tx, before):
                        for attempt in tx.progress.quiz_attempts:
                            if attempt.question_id == before.interaction_id:
                                attempt.independent = False
                                attempt.visual_context['assistance'] = assistance(before)
                        kp_id = before.question.knowledge_point_id
                        tx.progress.mastery_levels[kp_id] = LearningService(self).calculate_mastery(tx.progress, kp_id)
                    tx.touch()
                    if isinstance(result, tuple) and result and getattr(result[0], 'interaction_id', None) == after.interaction_id:
                        result = (after, *result[1:])
            if review:
                from .review import commit_review_action
                commit_review_action(tx, review)
            changed = {e.knowledge_point_id for e in tx.progress.learning_evidence if e.evidence_id not in old_evidence}
            if repair and before is not None:
                changed.add(before.question.knowledge_point_id)
            if changed:
                from .review import sync_schedule
                sync_schedule(self, tx, changed)
            if command and command['path_id'] == book_id:
                current = tx.get_interaction(command['question_id'])
                receipts = current.result.setdefault('host_commands', {})
                if len(receipts) >= 128:
                    raise MasteryInteractionError('question_command_budget_exceeded')
                receipts[command['command_id']] = command['signature']
                if command['action'] == 'answer' and 'self_confidence' not in current.result:
                    current.result['self_confidence'] = command['confidence']
                tx.put_interaction(current)
            return result

        return super().mutate(book_id, guarded, **kwargs)

    @staticmethod
    def _teaching_after(tx, interaction):
        return tx.progress.explained_objectives.get(interaction.question.knowledge_point_id, {}).get(
            'timestamp', 0) > interaction.question.created_at

    def _assistance(self, tx, interaction, event):
        help_used = assistance(interaction)
        independent = not help_used['events'] and not self._teaching_after(tx, interaction)
        event.hints_used = help_used['hints_used']
        event.visual_context.update(assistance=help_used, independent=independent,
                                    teaching_after_question=self._teaching_after(tx, interaction))
        if not independent and event.result == 'correct':
            event.quality = min(event.quality or 1., .6)  # 沿用原生辅助正确证据的质量上限。


class HostAssessmentService(LearningService):
    def grade_interaction(self, *args, **kwargs):
        # 辅助/核验标记落定后，同一事务内由原生调度器重放。
        kwargs['scheduler'] = None
        return super().grade_interaction(*args, **kwargs)

    def record_qualitative_for_path(self, *args, **kwargs):
        kwargs['scheduler'] = None
        return super().record_qualitative_for_path(*args, **kwargs)

    def repair_question(self, book_id, question_id='', **kwargs):
        if not question_id:
            raise MasteryInteractionError('question_id_required')
        if kwargs.get('action') == 'correct' and _review.get() is None:
            raise MasteryInteractionError('question_review_required')
        token = _repair.set({'path_id': book_id, 'question_id': question_id, 'action': kwargs.get('action')})
        try:
            kwargs['scheduler'] = None
            return super().repair_question(book_id, question_id, **kwargs)
        finally:
            _repair.reset(token)
