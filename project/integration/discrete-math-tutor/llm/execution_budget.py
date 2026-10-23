"""同一活动回合共享绝对时限；等待 ask_user 不保存进程内时钟。"""
from contextvars import ContextVar, copy_context
from functools import wraps
from queue import Queue, Empty
from threading import Event, Lock, Thread
from time import monotonic

current_budget = ContextVar("active_execution_budget", default=None)


class BudgetExceeded(RuntimeError):
    pass


class ExecutionBudget:
    def __init__(self, seconds=120):
        self.started = monotonic()
        self.deadline = self.started + seconds
        self.seconds = seconds
        self.stopped = Event()
        self.events = []
        self.lock = Lock()

    def remaining(self):
        value = self.deadline - monotonic()
        if self.stopped.is_set() or value <= 0:
            self.stopped.set()
            raise BudgetExceeded("本轮活动总时限已到，未完成内容不发布。")
        return value

    def call(self, stage, callback):
        remaining = self.remaining()
        started = monotonic()
        queue = Queue(maxsize=1)
        context = copy_context()
        def run():
            try:
                self.remaining()
                queue.put((True, context.run(callback)))
            except BaseException as exc:
                queue.put((False, exc))
        # 同步 IO 无法强杀；超时后 guard 阻止晚到 token、后续模型及保存。
        Thread(target=run, daemon=True).start()
        outcome = "ok"
        try:
            try:
                ok, value = queue.get(timeout=remaining)
            except Empty:
                self.stopped.set()
                raise BudgetExceeded("本轮活动总时限已到，未完成内容不发布。") from None
            self.remaining()
            if not ok:
                raise value
            return value
        except BaseException:
            outcome = "failed"
            raise
        finally:
            with self.lock:
                self.events.append({"stage": stage, "start_ms": round((started-self.started)*1000),
                    "elapsed_ms": round((monotonic()-started)*1000), "outcome": outcome})

    def record(self, stage, **data):
        with self.lock:
            self.events.append({'stage': stage, 'at_ms': round((monotonic()-self.started)*1000), **data})

    def snapshot(self):
        with self.lock:
            return {"active_limit_seconds": self.seconds,
                    "elapsed_ms": round((monotonic()-self.started)*1000), "stages": list(self.events)}


def check_budget():
    budget = current_budget.get()
    if budget:
        budget.remaining()


def stage_call(stage, callback):
    budget = current_budget.get()
    return budget.call(stage, callback) if budget else callback()


def bounded_stage(stage):
    def decorate(method):
        @wraps(method)
        def run(*args, **kwargs):
            return stage_call(stage, lambda: method(*args, **kwargs))
        return run
    return decorate


def bounded_model(method):
    return bounded_stage("model." + method.__name__)(method)


def model_timeout(cap=None):
    budget = current_budget.get()
    if budget is None:
        return cap
    import httpx
    remaining = min(budget.remaining(), cap or float("inf"))
    return httpx.Timeout(remaining, connect=min(10, remaining), read=min(30, remaining))
