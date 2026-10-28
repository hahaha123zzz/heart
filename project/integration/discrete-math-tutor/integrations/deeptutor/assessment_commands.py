"""受控宿主命令，复用原生LearningService；公开投影始终使用白名单。"""
from copy import deepcopy
import math
import re
import time

from deeptutor.learning.pending import public_pending_question
from deeptutor.learning.service import MasteryInteractionError
from .assessment_store import assessment_command, assistance, reviewed_decision, reviewed_question


class AssessmentCommands:
    def __init__(self, service):
        self.service, self.store = service, service.store

    def _get(self, path_id, question_id):
        item = self.store.get_interaction(path_id, question_id)
        if item is None:
            raise MasteryInteractionError('question_not_found')
        return item

    def register(self, path_id, question, *, reviewer_id, key_version, sources, rubric=(), evidence_decision=None):
        if evidence_decision is not None and not evidence_decision.allowed:
            raise MasteryInteractionError('assessment_evidence_insufficient')
        if evidence_decision is not None and (evidence_decision.mode == 'mock' or not evidence_decision.source_ids
                or not set(evidence_decision.source_ids) <= {s.get('source_id') for s in sources}):
            raise MasteryInteractionError('assessment_evidence_unverified')
        if (len(rubric) > 8 or len({c['id'] for c in rubric}) != len(rubric)
                or any(not c['id'].strip() or not c['description'].strip() for c in rubric)):
            raise MasteryInteractionError('invalid_rubric')
        existing = self.store.get_interaction(path_id, question.question_id)
        if existing:
            if existing.question.model_dump(exclude={'created_at'}) != question.model_dump(exclude={'created_at'}):
                raise MasteryInteractionError('assessment_question_conflict')
            return self.status(path_id, existing.interaction_id)
        with reviewed_question(path_id, question, reviewer_id=reviewer_id, key_version=key_version,
                               sources=sources, rubric=rubric):
            _, item, _ = self.service.register_question(path_id, question)
        return self.status(path_id, item.interaction_id)

    def status(self, path_id, question_id):
        item = self._get(path_id, question_id)
        progress = self.store.load(path_id)
        try:
            self.store._proof(path_id, item)
            source_status = 'verified'
        except (MasteryInteractionError, OSError, ValueError):
            source_status = 'unavailable'
        if source_status != 'verified':
            return {'interaction_id': question_id, 'path_id': path_id, 'revision': progress.version,
                    'status': item.status.value, 'source_status': 'unavailable', 'question': None,
                    'assessment': {'verification': 'unavailable'}}
        events = [e for e in progress.learning_evidence if e.knowledge_point_id == item.question.knowledge_point_id]
        reviewed = [e for e in events if e.visual_context.get('verification') in ('reviewed_key', 'reviewed_rubric')]
        help_used = assistance(item)
        output = {'interaction_id': item.interaction_id, 'path_id': path_id, 'revision': progress.version,
                  'status': item.status.value, 'question': public_pending_question(item.question).to_dict(),
                  'review_status': item.result.get('review_status', 'graded' if item.status.value == 'graded' else 'not_reviewed'),
                  'source_status': source_status,
                  'assistance': {k: v for k, v in help_used.items() if k != 'events'},
                  'evidence_summary': {'reviewed': len(reviewed),
                      'independent': sum(e.visual_context.get('independent') is True for e in reviewed),
                      'assisted': sum(e.visual_context.get('independent') is False for e in reviewed),
                      'unverified': len(events)-len(reviewed),
                      'latest_at': max((e.timestamp for e in reviewed), default=None)},
                  'self_confidence': {'value': item.result.get('self_confidence'), 'source': 'student_self_report'}}
        if item.status.value == 'graded':
            output['assessment'] = {'is_correct': item.result.get('is_correct'),
                'version': item.result.get('assessment_version'),
                'verification': 'recorded_source_changed' if source_status != 'verified' else
                                'voided' if item.result.get('review_invalidated') or item.result.get('repair', {}).get('action') == 'void' else 'reviewed',
                'misconception_hypotheses': deepcopy(item.result.get('misconception_hypotheses', []))}
        return output

    def run(self, path_id, question_id, *, command_id, action, text='', confidence=None,
            kind='hint', level=0, full_explanation=False, published=False, reviewer_id='', criteria=None,
            misconception_type='', source_quote=''):
        if not command_id or len(command_id) > 100 or len(text) > 4000:
            raise MasteryInteractionError('invalid_assessment_command')
        if confidence is not None and (type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1):
            raise MasteryInteractionError('invalid_self_confidence')
        if action == 'message':
            from agents.learning_feedback import is_self_report_understood, is_stuck
            from agents.teaching_policy import resolve_teaching_mode
            if re.fullmatch(r'(?:这题|这个问题)?(?:先)?(?:跳过|不做了|略过)[。！!\s]*', text):
                return self.run(path_id, question_id, command_id=command_id, action='skip', text=text)
            if re.fullmatch(r'(?:这题|这个知识点)?(?:先)?(?:延后|下次再做|下次再学)[。！!\s]*', text):
                return self.run(path_id, question_id, command_id=command_id, action='defer', text=text)
            if (is_self_report_understood(text) or is_stuck(text) or resolve_teaching_mode(text) != 'auto'
                    or re.match(r'^(?:请|先|另外|我想)?(?:解释|问|插问|为什么|什么是|只要例子|只给提示|回到)', text)
                    or re.search(r'答案(?:有误|错了)|题(?:目|干)?有歧义', text)):
                return dict(self.status(path_id, question_id), message_action='interjection', mastery_changed=False)
            return self.run(path_id, question_id, command_id=command_id, action='answer', text=text, confidence=confidence)
        payload = {'text': text, 'confidence': confidence, 'kind': kind, 'level': level,
            'full_explanation': full_explanation, 'published': published, 'reviewer_id': reviewer_id,
            'criteria': criteria, 'misconception_type': misconception_type, 'source_quote': source_quote}
        with assessment_command(path_id, question_id, command_id, action, payload):
            if action == 'present':
                self.service.mark_question_awaiting(path_id, interaction_id=question_id)
            elif action == 'answer':
                if not text.strip() or re.match(r'^(?:先插问|另外问|请解释|只(?:给|要)提示|我懂了|先跳过)', text.strip()):
                    raise MasteryInteractionError('answer_needs_clarification')
                current = self._get(path_id, question_id)
                if current.status.value in ('answered', 'graded') and current.user_answer != text:
                    raise MasteryInteractionError('answer_already_recorded')
                self.service.record_question_answer(path_id, text, interaction_id=question_id)
            elif action == 'grade':
                self.service.grade_interaction(path_id, question_id=question_id,
                    answer=self._get(path_id, question_id).user_answer)
            elif action == 'help':
                if not published or kind not in ('hint', 'example', 'explanation', 'source_view'):
                    raise MasteryInteractionError('published_help_required')
                if type(level) is not int or (kind == 'hint' and level not in (1, 2, 3)) or (kind != 'hint' and level):
                    raise MasteryInteractionError('invalid_hint_level')
                if full_explanation and kind != 'explanation':
                    raise MasteryInteractionError('invalid_full_explanation')
                def help_record(tx):
                    item = tx.get_interaction(question_id)
                    self.store._proof(path_id, item)
                    item.result.setdefault('assistance_events', []).append({'command_id': command_id,
                        'kind': kind, 'level': level, 'full_explanation': full_explanation, 'published_at': time.time()})
                    tx.put_interaction(item)
                    tx.emit('assessment.help_published', {'interaction_id': question_id, 'kind': kind, 'level': level})
                self.store.mutate(path_id, help_record)
            elif action == 'skip':
                self.service.abandon_active_question(path_id)
            elif action == 'defer':
                self.service.defer_objective(path_id, self._get(path_id, question_id).question.knowledge_point_id, note=text)
            elif action == 'void':
                self.service.repair_question(path_id, question_id, action='void', reason=text)
            elif action == 'review':
                item = self._get(path_id, question_id)
                if item.status.value == 'graded':
                    self.store.mutate(path_id, lambda tx: None)
                else:
                    if not reviewer_id.strip() or not criteria or any(v not in ('met', 'not_met', 'unavailable') for v in criteria.values()):
                        raise MasteryInteractionError('qualitative_rubric_review_required')
                    if 'unavailable' in criteria.values():
                        def ungraded(tx):
                            current = tx.get_interaction(question_id)
                            self.store._proof(path_id, current)
                            current.result['review_status'] = 'ungraded'
                            tx.put_interaction(current)
                            tx.emit('assessment.review_unavailable', {'interaction_id': question_id})
                        self.store.mutate(path_id, ungraded)
                        return dict(self.status(path_id, question_id), review_status='ungraded')
                    decision = {'question_id': question_id, 'answer': item.user_answer, 'reviewer_id': reviewer_id,
                                'criteria': criteria, 'decision_id': command_id}
                    with reviewed_decision(decision):
                        self.service.record_qualitative_for_path(path_id, item.question.knowledge_point_id,
                            passed=all(v == 'met' for v in criteria.values()), evidence=text,
                            session_id=item.session_id, turn_id=question_id + ':' + command_id)
            elif action in ('hypothesis', 'dismiss_hypothesis', 'resolve_hypothesis'):
                from models.misconception import CANONICAL_TYPES, normalize_type
                name = normalize_type(misconception_type)
                if name not in CANONICAL_TYPES:
                    raise MasteryInteractionError('unknown_misconception_type')
                def hypothesis(tx):
                    item = tx.get_interaction(question_id)
                    if item.status.value != 'graded' or item.result.get('is_correct') is not False:
                        raise MasteryInteractionError('misconception_requires_reviewed_attempt')
                    rows = item.result.setdefault('misconception_hypotheses', [])
                    record = next((r for r in rows if r['type'] == name), None)
                    if action == 'hypothesis':
                        self.store._proof(path_id, item)
                        if not source_quote.strip() or source_quote not in item.user_answer:
                            raise MasteryInteractionError('misconception_quote_not_in_answer')
                        if record is None:
                            rows.append({'type': name, 'description': CANONICAL_TYPES[name], 'status': 'hypothesis',
                                'question_id': question_id, 'student_quote': source_quote,
                                'verification': 'candidate_not_confirmed'})
                    elif record:
                        record['status'] = 'dismissed' if action == 'dismiss_hypothesis' else 'resolved'
                    else:
                        raise MasteryInteractionError('misconception_not_found')
                    tx.put_interaction(item)
                    tx.emit('assessment.misconception_changed', {'interaction_id': question_id, 'type': name, 'action': action})
                self.store.mutate(path_id, hypothesis)
            else:
                raise MasteryInteractionError('unknown_assessment_action')
        return self.status(path_id, question_id)

    def correct(self, path_id, question_id, *, command_id, expected_answer, reviewer_id, key_version, sources, reason):
        item = self._get(path_id, question_id)
        if item.question.question_type != 'choice':
            raise MasteryInteractionError('qualitative_revision_requires_new_question')
        question = item.question.model_copy(deep=True, update={'expected_answer': expected_answer})
        if expected_answer not in question.choice_map:
            raise MasteryInteractionError('invalid_answer_key')
        with reviewed_question(path_id, question, reviewer_id=reviewer_id, key_version=key_version, sources=sources):
            with assessment_command(path_id, question_id, command_id, 'correct',
                                    {'expected_answer': expected_answer, 'reviewer_id': reviewer_id,
                                     'key_version': key_version, 'reason': reason, 'sources': sources}):
                self.service.repair_question(path_id, question_id, action='correct', expected_answer=expected_answer, reason=reason)
        return self.status(path_id, question_id)
