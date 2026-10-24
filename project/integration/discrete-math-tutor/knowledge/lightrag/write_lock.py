"""One nonblocking writer per knowledge base, shared across worker processes."""

from collections.abc import Iterator
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path

from .indexing_policy import IndexingPolicyError


@contextmanager
def write_ownership(kb_dir: Path) -> Iterator[None]:
    """Hold exclusive nonblocking write ownership for a knowledge base.

    Yields:
        None while the cross-process indexing lock is held.

    Raises:
        IndexingPolicyError: The target uses a symlink or another writer owns it."""
    kb_dir = Path(kb_dir)
    if (kb_dir.is_symlink() or (kb_dir.exists() and bool(getattr(kb_dir.lstat(), "st_file_attributes", 0) & 0x400))):
        raise IndexingPolicyError("A writable knowledge-base directory cannot be a symbolic link.")
    lock_dir = kb_dir.parent / ".lightrag-locks"
    if (lock_dir.is_symlink() or (lock_dir.exists() and bool(getattr(lock_dir.lstat(), "st_file_attributes", 0) & 0x400))):
        raise IndexingPolicyError("The indexing lock directory cannot be a symbolic link.")
    lock_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(str(kb_dir.resolve()).encode("utf-8")).hexdigest()
    lock_path = lock_dir / f"{key}.lock"
    if (lock_path.is_symlink() or (lock_path.exists() and bool(getattr(lock_path.lstat(), "st_file_attributes", 0) & 0x400))):
        raise IndexingPolicyError("The indexing lock cannot be a symbolic link.")
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "r+b") as handle:
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise IndexingPolicyError(
                "Another indexing operation is active for this knowledge base; resubmit after it finishes."
            ) from exc
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


# 同进程只排同一候选；保留原跨进程非阻塞所有权，不引入引擎池。
from contextlib import asynccontextmanager
import asyncio
import threading
import time
_query_guard = threading.Lock()
_query_locks = {}

@asynccontextmanager
async def query_ownership(candidate, cancellation=None, *, wait_seconds=180):
    from llm.execution_budget import check_budget, current_budget
    key = str(Path(candidate).resolve())
    with _query_guard:
        if key not in _query_locks:
            if len(_query_locks) >= 32:
                raise IndexingPolicyError('候选查询队列容量已满，请稍后重试')
            _query_locks[key] = {'lock':threading.Lock(),'users':0}
        entry = _query_locks[key]
        if entry['users'] >= 8:
            raise IndexingPolicyError('当前候选等待队列已满，请稍后重试')
        entry['users'] += 1
    acquired = False
    started = time.monotonic()
    try:
        while not acquired:
            check_budget()
            if cancellation is not None: cancellation.check()
            if time.monotonic()-started >= wait_seconds:
                raise TimeoutError('等待候选查询所有权超时，请稍后重试')
            acquired = entry['lock'].acquire(False)
            if not acquired: await asyncio.sleep(.05)
        check_budget()
        if cancellation is not None: cancellation.check()
        with write_ownership(candidate):
            yield time.monotonic()-started
    finally:
        if acquired: entry['lock'].release()
        with _query_guard:
            entry['users'] -= 1
            if not entry['users']: _query_locks.pop(key,None)
