"""宿主原生路径交接：适配上游绑定表/租约，避免普通失败产生半次切换。"""
import asyncio
import hashlib
import inspect
import json
from pathlib import Path
import sqlite3
import time

from .client import BackendUnavailable


def _handoff(context, path_id, session_id, turn_id, *, leave, session_db):
    from deeptutor.capabilities.mastery.binding import PathBindingError
    from deeptutor.learning.models import LearningProgress
    from deeptutor.learning.identity import sanitize_mastery_path_id
    from deeptutor.learning.event_hub import publish_topic_signal
    from deeptutor.multi_user.context import get_current_user
    from deeptutor.services.session.workspace_preferences import upgrade_workspace_preferences
    from deeptutor.services.workspace import get_content_workspace_service
    from .learning_write_guard import HostAuthorizedLearningStore

    if session_id != context.session_id or not turn_id:
        raise PathBindingError('路径交接的会话与宿主请求不匹配')
    root = get_current_user().scope.root.resolve()
    if not isinstance(session_db, Path) or not session_db.is_file() or not session_db.resolve().is_relative_to(root):
        raise PathBindingError('会话库不属于当前原生账户，停止路径交接')
    target = sanitize_mastery_path_id(session_id if leave else path_id)
    store = HostAuthorizedLearningStore(context.check)
    workspace = get_content_workspace_service().binding_by_id(context.workspace_id)
    if not workspace.root.resolve().is_relative_to(root) or not store.db_path.resolve().is_relative_to(workspace.root.resolve()):
        raise PathBindingError('学习库不属于当前原生工作区')
    now = time.time()
    with store._connect() as conn:
        conn.execute('ATTACH DATABASE ? AS native_session', (str(session_db.resolve()),))
        conn.execute('BEGIN IMMEDIATE')
        try:
            actor = conn.execute('''SELECT t.status FROM native_session.turns t
                JOIN native_session.turn_submissions s ON s.turn_id=t.id
                WHERE t.id=? AND t.session_id=? AND s.session_id=? AND s.client_submission_id=? AND s.workspace_id=?''',
                (turn_id, session_id, session_id, context.submission_id, context.workspace_id)).fetchone()
            if actor is None or actor['status'] not in ('running', 'waiting_input'):
                raise PathBindingError('路径交接不属于当前活动原生回合')
            session = conn.execute('SELECT preferences_json FROM native_session.sessions WHERE id=?', (session_id,)).fetchone()
            if session is None:
                raise PathBindingError('原生会话已删除')
            preferences = json.loads(session['preferences_json'] or '{}')
            if not isinstance(preferences, dict):
                raise PathBindingError('原生会话偏好无效')
            row = conn.execute('SELECT revision FROM mastery_paths WHERE path_id=?', (target,)).fetchone()
            if row is None and not leave:
                raise PathBindingError('目标路径不存在，请重新查看路径列表')
            topic = conn.execute('SELECT status FROM mastery_topic_meta WHERE path_id=?', (target,)).fetchone()
            if topic is not None and topic['status'] == 'archived':
                raise PathBindingError('目标路径尚未激活或已归档')
            busy = conn.execute('SELECT turn_id FROM mastery_path_leases WHERE path_id=?', (target,)).fetchone()
            if busy is not None and busy['turn_id'] != turn_id:
                raise PathBindingError('目标路径正在其他回合中学习，原位置保持不变')
            other = conn.execute('SELECT 1 FROM mastery_path_leases WHERE session_id=? AND turn_id<>?', (session_id, turn_id)).fetchone()
            if other is not None:
                raise PathBindingError('该会话仍有其他回合持有路径租约')
            previous = conn.execute('SELECT path_id FROM mastery_path_sessions WHERE session_id=?', (session_id,)).fetchone()
            previous = previous['path_id'] if previous else ''
            if row is None:
                progress = LearningProgress(book_id=target)
                conn.execute('INSERT INTO mastery_paths(path_id,state_json,revision,created_at,updated_at) VALUES (?,?,1,?,?)',
                    (target, store._progress_payload(progress, 1, now), progress.created_at, now))
                conn.execute("INSERT INTO mastery_events(path_id,revision,event_type,payload_json,created_at) VALUES (?,1,'path.created','{}',?)", (target, now))
            conn.execute('DELETE FROM mastery_path_leases WHERE turn_id=?', (turn_id,))
            conn.execute('INSERT INTO mastery_path_leases(path_id,session_id,turn_id,acquired_at) VALUES (?,?,?,?)',
                         (target, session_id, turn_id, now))
            conn.execute('DELETE FROM mastery_path_sessions WHERE session_id=? AND path_id<>?', (session_id, target))
            conn.execute('''INSERT INTO mastery_path_sessions(path_id,session_id,created_at,last_seen_at) VALUES (?,?,?,?)
                ON CONFLICT(path_id,session_id) DO UPDATE SET last_seen_at=excluded.last_seen_at''', (target, session_id, now, now))
            if leave:
                conn.execute("UPDATE mastery_paths SET owner_session_id=? WHERE path_id=? AND owner_session_id=''", (session_id, target))
            preferences = upgrade_workspace_preferences({**preferences, 'mastery_path_id': '' if leave else target})
            conn.execute('UPDATE native_session.sessions SET preferences_json=?,updated_at=? WHERE id=?',
                         (json.dumps(preferences, ensure_ascii=False), now, session_id))
            revision = conn.execute('SELECT revision FROM mastery_paths WHERE path_id=?', (target,)).fetchone()['revision']
            old = conn.execute('SELECT revision FROM mastery_paths WHERE path_id=?', (previous,)).fetchone()
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    publish_topic_signal(target, revision, 'session.bound', scope=store.event_scope)
    if previous and previous != target and old is not None:
        publish_topic_signal(previous, old['revision'], 'session.released', scope=store.event_scope)
    return target


async def _managed_handoff(context, *, path_id='', session_id, turn_id, bind_turn, leave=False, require_existing=True):
    from deeptutor.capabilities.mastery.binding import PathBindingError
    from deeptutor.services.session import get_session_store

    if bind_turn is not None and (not callable(bind_turn) or inspect.iscoroutinefunction(bind_turn)):
        raise PathBindingError('当前回合的路径更新回调无效')
    if not leave and not require_existing:
        raise PathBindingError('宿主路径切换不能隐式创建未确认路径')
    try:
        target = await asyncio.to_thread(_handoff, context, path_id, session_id, turn_id,
            leave=leave, session_db=getattr(get_session_store(), 'db_path', None))
    except sqlite3.DatabaseError as exc:
        raise PathBindingError('路径交接未提交，原位置保留') from exc
    if bind_turn is not None:
        try:
            bind_turn(target)
        except Exception as exc:
            raise PathBindingError('路径位置已保存，但当前回合同步失败，请恢复会话后继续') from exc
    return target


def install_learning_binding_adapter():
    from deeptutor.capabilities.mastery import binding
    from .worker import VENDOR_ROOT

    if all(getattr(function, '_heart_scoped_binding', False) for function in (binding.rebind_active_path, binding.leave_active_path)):
        return
    if any(function.__module__ != binding.__name__ for function in (binding.rebind_active_path, binding.leave_active_path)):
        raise BackendUnavailable('原生路径交接实现已被其他实现替换')
    source = VENDOR_ROOT / 'deeptutor/capabilities/mastery/binding.py'
    pin = json.loads((VENDOR_ROOT / 'UPSTREAM_SNAPSHOT.json').read_text(encoding='utf-8'))
    if Path(binding.__file__).resolve() != source.resolve():
        raise BackendUnavailable('原生路径交接与固定源码不一致')
    for relative in ('deeptutor/capabilities/mastery/binding.py', 'deeptutor/learning/storage.py',
                     'deeptutor/services/session/sqlite_store.py', 'deeptutor/services/session/workspace_preferences.py'):
        if hashlib.sha256((VENDOR_ROOT / relative).read_bytes()).hexdigest() != pin['files'][relative]:
            raise BackendUnavailable('原生路径交接依赖与固定源码不一致')
    original_switch, original_leave = binding.rebind_active_path, binding.leave_active_path

    async def switch(**kwargs):
        from .learning_tool_adapter import current_learning_context
        context = current_learning_context()
        if context is None:
            return await original_switch(**kwargs)
        return await _managed_handoff(context, **kwargs)

    async def leave(**kwargs):
        from .learning_tool_adapter import current_learning_context
        context = current_learning_context()
        if context is None:
            return await original_leave(**kwargs)
        return await _managed_handoff(context, leave=True, **kwargs)

    switch._heart_scoped_binding = True
    leave._heart_scoped_binding = True
    binding.rebind_active_path, binding.leave_active_path = switch, leave
