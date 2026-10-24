"""请求内的临时正文事件；不写历史、工具记录或学习状态。"""
from contextvars import ContextVar
from uuid import uuid4

current_answer = ContextVar('current_answer', default=None)


class AnswerEvents:
    def __init__(self, emit):
        self.emit = emit
        self.identity = None
        self.round_id = 0
        self.seq = 0
        self.binding = None

    def bind(self, identity, guard, stream_guard=None):
        self.binding = identity, guard
        self.stream_guard = stream_guard or guard

    def guard(self):
        if self.binding:
            self.stream_guard()

    def validate(self):
        if self.binding:
            self.binding[1]()

    def send(self, event, **data):
        if self.identity is None:
            return
        self.seq += 1
        self.emit(event, {**self.identity, 'round_id': self.round_id, 'seq': self.seq, **data})

    def begin(self):
        self.validate()
        if self.identity:
            self.send('answer_replace', text='')
        else:
            self.identity = {**self.binding[0](), 'answer_id': str(uuid4())}
        self.round_id += 1
        self.send('answer_state', state='generating')

    def delta(self, text):
        # 正文先留在模型调用结果中；教学/引用检查通过并持久化后，
        # finish() 才会把权威最终稿分块发送到页面。
        self.guard()

    def checking(self):
        if self.identity:
            self.validate()
            self.send('answer_state', state='checking')

    def retract(self):
        if self.identity:
            self.guard()
            self.send('answer_replace', text='')
            self.send('answer_state', state='retrieving')

    def finish(self, result):
        # 调用方已通过收据/epoch 检查；完成态不再调用只接受执行态的 guard。
        if self.identity:
            saved = result.get('answer_status') == 'answered'
            self.send('answer_replace', text='')
            if saved:
                text = str(result.get('reply') or '')
                self.send('answer_state', state='generating')
                # 仅发布已落库的最终版本；分块保留页面的流式呈现体验。
                for offset in range(0, len(text), 80):
                    self.send('answer_delta', text=text[offset:offset + 80])
                self.send('answer_replace', text=text)
            self.send('answer_state', state='saved' if saved else 'rejected')


def answer_kwargs():
    answer = current_answer.get()
    if answer is None or answer.binding is None:
        return {}
    answer.begin()
    return {'on_delta': answer.delta, 'stream_guard': answer.guard}


def checking():
    answer = current_answer.get()
    if answer:
        answer.checking()


def retract():
    answer = current_answer.get()
    if answer:
        answer.retract()
