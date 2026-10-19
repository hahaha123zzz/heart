"""In-process cancellation registry for Q3 turns.

The database status remains the cross-process authority; this registry makes
an HTTP cancel reach the running loop promptly in the same worker.
"""
from __future__ import annotations

from threading import RLock

from agents.tool_protocol import Cancellation

_LOCK = RLock()
_ACTIVE: dict[str, Cancellation] = {}


def register(task_id: str) -> Cancellation:
    with _LOCK:
        token = _ACTIVE.get(task_id)
        if token is None:
            token = Cancellation()
            _ACTIVE[task_id] = token
        return token


def get(task_id: str) -> Cancellation | None:
    with _LOCK:
        return _ACTIVE.get(task_id)


def cancel(task_id: str) -> bool:
    with _LOCK:
        token = _ACTIVE.get(task_id)
        if token is None:
            return False
        token.cancel()
        return True


def release(task_id: str) -> None:
    with _LOCK:
        _ACTIVE.pop(task_id, None)
