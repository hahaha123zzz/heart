"""请求内的临时正文事件；不写历史、工具记录或学习状态。"""
from contextvars import ContextVar
from uuid import uuid4
from llm.execution_budget import check_budget, current_budget

current_answer = ContextVar('current_answer', default=None)


class AnswerEvents:
    def __init__(self, emit):
        self.emit = emit
        self.identity = None
        self.round_id = 0
        self.seq = 0
        self.binding = None
        self.role = "answer"
        self.visible_round = None
        self.text = ""

    def bind(self, identity, guard, stream_guard=None):
        self.binding = identity, guard
        self.stream_guard = stream_guard or guard

    def guard(self):
        check_budget()
        if self.binding:
            self.stream_guard()

    def validate(self):
        if self.binding:
            self.binding[1]()

    def send(self, event, **data):
        if self.identity is None:
            return
        self.seq += 1
        self.emit(event, {**self.identity, 'round_id': self.round_id, 'seq': self.seq, 'role': self.role, **data})

    def begin(self, role="answer"):
        self.validate()
        if self.identity is None:
            self.identity = {**self.binding[0](), 'answer_id': str(uuid4())}
        self.role = role
        if role == "answer":
            self.text = ""
            if current_budget.get():
                current_budget.get().record("answer.start")
        self.round_id += 1
        self.send('answer_state', state='generating' if role == 'answer' else 'retrieving')

    def delta(self, text):
        self.guard()
        if self.role == 'answer':
            if not self.text and current_budget.get():
                current_budget.get().record('answer.first_token', round_id=self.round_id)
            self.text += text
            self.visible_round = self.round_id
            self.send('answer_delta', text=text)

    def checking(self):
        if self.identity:
            self.validate()
            self.send('answer_state', state='checking')

    def retract(self):
        if self.identity:
            self.guard()
            if self.role == 'answer' and self.visible_round == self.round_id:
                self.send('answer_replace', text='', target_round_id=self.round_id, reason='candidate_rejected')
            self.send('answer_state', state='retrieving')

    def finish(self, result):
        # 调用方已通过收据/epoch 检查；完成态不再调用只接受执行态的 guard。
        if self.identity:
            saved = result.get('answer_status') == 'answered'
            self.role = 'answer'
            self.send('answer_replace', text=str(result.get('reply') or '') if saved else '', authoritative=True)
            state = {'answer_interrupted':'interrupted','incomplete_answer':'incomplete','active_timeout':'timeout'}.get(result.get('answer_status'), 'rejected')
            self.send('answer_state', state='saved' if saved else state)


def answer_kwargs(role="answer"):
    answer = current_answer.get()
    if answer is None or answer.binding is None:
        return {}
    answer.begin(role)
    return {'on_delta': answer.delta, 'stream_guard': answer.guard}


def checking():
    answer = current_answer.get()
    if answer:
        answer.checking()


def retract():
    answer = current_answer.get()
    if answer:
        answer.retract()
