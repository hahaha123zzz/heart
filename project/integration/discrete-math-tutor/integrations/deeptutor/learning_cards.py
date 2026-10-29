"""原生交互卡片投影；动作仍调用TA2服务，展示状态放在原interaction中。"""
from copy import deepcopy
import hashlib

from deeptutor.learning.service import MasteryInteractionError
from .assessment_store import assistance


class NativeLearningCards:
    def __init__(self, commands):
        self.commands, self.store = commands, commands.store

    def identity(self, path_id, question_id, kind):
        check = self.store._host_check
        scope = ':'.join(check[key] for key in ('student_id', 'course_id', 'session_id'))
        return hashlib.sha256(f'{scope}:{path_id}:{question_id}:{kind}'.encode()).hexdigest()[:24]

    def configure(self, path_id, question_id, *, hints, full_explanation, presentations):
        """仅可信宿主可提交已审核的帮助；模型和学生无此权限。"""
        from agents.learning_cards import presentation_arguments
        checked = [presentation_arguments(p) for p in presentations]
        if any(p is None for p in checked) or len({p['kind'] for p in checked}) != len(checked):
            raise MasteryInteractionError('invalid_card_presentation')
        support = {'hints': hints, 'full_explanation': full_explanation, 'presentations': checked}
        def register(tx):
            item = tx.get_interaction(question_id)
            proof = deepcopy(self.store._proof(path_id, item))
            if item.status.value not in ('registered', 'awaiting_input'):
                raise MasteryInteractionError('assessment_already_answered')
            if proof.get('card_support') == support:
                return
            if proof.get('card_support'):
                raise MasteryInteractionError('card_support_already_registered')
            proof['card_support'] = support
            proof['seal'] = self.store._seal(path_id, item.question, proof)
            item.result['host_assessment'] = proof
            tx.put_interaction(item)
            tx.emit('assessment.card_support_registered', {'interaction_id': question_id})
        self.store.mutate(path_id, register)
        return self.deck(path_id, question_id)

    def deck(self, path_id, question_id):
        status = self.commands.status(path_id, question_id)
        if status['source_status'] != 'verified':
            return {'learning_cards': [], 'source_status': 'unavailable', 'revision': status['revision']}
        item = self.commands._get(path_id, question_id)
        proof = item.result['host_assessment']
        support = proof.get('card_support', {})
        state = item.result.get('card_view', {})
        def card(kind, title, content, actions):
            card_id = self.identity(path_id, question_id, kind)
            return {'schema': 'learning-cards/v2', 'card_id': card_id, 'kind': kind, 'title': title,
                'revision': status['revision'], 'interaction_id': question_id,
                'objective_id': item.question.knowledge_point_id, 'path_id': path_id,
                'source_refs': [{'source_id': s.get('source_id'), 'document_id': s['document_id'],
                                 'version': s['version']} for s in proof['sources']],
                'allowed_actions': actions, 'expanded': state.get(card_id, []), **content}
        active = status['status'] in ('registered', 'awaiting_input')
        answered = status['status'] == 'answered'
        actions = ['submit_answer', 'defer', 'skip'] if active else ['grade'] if answered and item.question.question_type == 'choice' else []
        if active and support.get('hints'):
            actions.append('request_hint')
        if (active or answered) and support.get('full_explanation'):
            actions.append('view_explanation')
        # 宿主session_id与原生session_id不同，只向已绑定路径提供返回动作。
        from .learning_tool_adapter import current_learning_context
        context = current_learning_context()
        can_return = context is not None and self.store.path_id_for_session(context.session_id) == path_id
        if can_return:
            actions.append('return_path')
        q = card('assessment_question', '教材测评', {'question': status['question'], 'status': status['status'],
            'learner_answer': item.user_answer,
            'disposition': item.result.get('card_disposition'),
            'assessment': status.get('assessment'), 'feedback': item.result.get('published_help'),
            'assistance': status['assistance'], 'review_status': status['review_status']}, actions)
        cards = [q]
        # 带答案的分步讲解和对比仅在明确查看解释后公开，不把隐藏DOM当保密。
        if item.result.get('card_explanation_requested'):
            for p in support.get('presentations', []):
                cards.append(card(p['kind'], p['title'], deepcopy(p), ['set_expanded']))
        cards.append(card('learning_progress', '学习证据', {'explained': status['explained'],
            'pending': active or answered, 'formative_attempts': 0, 'mastered': False,
            'evidence_summary': status['evidence_summary'], 'assistance': status['assistance']},
            ['set_expanded'] + (['return_path'] if can_return else [])))
        return {'learning_cards': cards, 'source_status': 'verified', 'revision': status['revision'],
                'navigation': item.result.get('card_return_path')}

    def act(self, path_id, question_id, *, card_id, action, command_id, base_revision, text='', expanded=()):
        deck = self.deck(path_id, question_id)
        selected = next((c for c in deck['learning_cards'] if c['card_id'] == card_id), None)
        if selected is None:
            raise MasteryInteractionError('card_not_found')
        item = self.commands._get(path_id, question_id)
        payload = {'card_id': card_id, 'action': action, 'text': text,
                   'expanded': list(expanded), 'base_revision': base_revision}
        receipt = item.result.get('card_commands', {}).get(command_id)
        if receipt is not None:
            if receipt != payload:
                raise MasteryInteractionError('assessment_command_conflict')
            return deck
        pending = item.result.get('card_requests', {}).get(command_id)
        if pending and pending['payload'] != payload:
            raise MasteryInteractionError('assessment_command_conflict')
        if pending is None and action not in selected['allowed_actions']:
            raise MasteryInteractionError('card_action_not_allowed')
        if action == 'set_expanded' and any(n > len(selected.get('steps', [])) for n in expanded):
            raise MasteryInteractionError('invalid_expansion')
        support = item.result['host_assessment'].get('card_support', {})
        # 收据和原始请求先占位，重试沿用原动作参数；实际评分去重仍由原生服务负责。
        def reserve(tx):
            current = tx.get_interaction(question_id)
            self.store._proof(path_id, current)
            receipts = current.result.setdefault('card_requests', {})
            if command_id in receipts:
                if receipts[command_id]['payload'] != payload:
                    raise MasteryInteractionError('assessment_command_conflict')
                return receipts[command_id]
            if tx.progress.version != base_revision:
                raise MasteryInteractionError('card_revision_conflict')
            if len(receipts) >= 128:
                raise MasteryInteractionError('question_command_budget_exceeded')
            level = min(3, assistance(current)['max_hint_level'] + 1) if action == 'request_hint' else 0
            receipts[command_id] = {'payload': deepcopy(payload), 'hint_level': level}
            tx.put_interaction(current)
            return receipts[command_id]
        _, reservation = self.store.mutate(path_id, reserve)
        key = hashlib.sha256(command_id.encode()).hexdigest()
        if action == 'submit_answer':
            self.commands.run(path_id, question_id, command_id=key+'a', action='answer', text=text)
            if item.question.question_type == 'choice':
                self.commands.run(path_id, question_id, command_id=key+'g', action='grade')
        elif action == 'grade':
            self.commands.run(path_id, question_id, command_id=key+'g', action='grade')
        elif action in ('defer', 'skip'):
            self.commands.run(path_id, question_id, command_id=key, action=action)
        elif action in ('request_hint', 'view_explanation'):
            level = reservation['hint_level']
            body = support['hints'][level-1] if action == 'request_hint' else support['full_explanation']
            self.commands.run(path_id, question_id, command_id=key, action='help',
                kind='hint' if action == 'request_hint' else 'explanation',
                level=level if action == 'request_hint' else 0, full_explanation=action == 'view_explanation',
                published=True, text=body)
        def finish(tx):
            current = tx.get_interaction(question_id)
            if action == 'set_expanded':
                current.result.setdefault('card_view', {})[card_id] = list(expanded)
            if action == 'view_explanation':
                current.result['card_explanation_requested'] = True
            if action in ('defer', 'skip'):
                current.result['card_disposition'] = action
            if action in ('defer', 'skip'):
                current.result['card_disposition'] = action
            if action == 'return_path':
                current.result['card_return_path'] = {'path_id': path_id, 'objective_id': current.question.knowledge_point_id}
            current.result.setdefault('card_commands', {})[command_id] = deepcopy(payload)
            tx.put_interaction(current)
            tx.emit('assessment.card_action', {'interaction_id': question_id, 'card_id': card_id, 'action': action})
        self.store.mutate(path_id, finish)
        return self.deck(path_id, question_id)
