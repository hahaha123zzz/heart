"""宿主受控课程查询：唯一执行者是已由 fixed_book 常驻的 LightRAG 后端。

worker 只沿本机桥接令牌调用；查询前后都回查宿主任务身份，取消、断连与预算
都会释放本次查询。这里不初始化第二份图谱，也不接受路径或未授权 KB 标识。
"""
import asyncio
import hashlib
import json
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request

from .native_contract import CourseSearchRequest, NativeUserCourseSearchRequest
from .session_bridge import require_bridge_token

router = APIRouter(prefix='/internal/heart/native', dependencies=[Depends(require_bridge_token)])
QUERY_BUDGET_SECONDS = 120
SOURCE_FIELDS = ('document_id', 'version', 'source_id', 'chapter_id', 'section_id', 'text',
                 'quote', 'page', 'image_refs', 'location')


def project(result):
    """只裁投影字段；原文身份、版本与映射 location 原样保留。"""
    return {
        'provider': result.get('provider'),
        'sdk': result.get('sdk'),
        'status': result.get('status'),
        'mode': result.get('mode'),
        'input_signature': result.get('input_signature'),
        'citation_status': result.get('citation_status'),
        'rerank_status': result.get('rerank_status'),
        'sources': [{key: source[key] for key in SOURCE_FIELDS if key in source}
                    for source in result.get('sources') or []],
        'visuals': result.get('visuals') or [],
        'graph_context': result.get('graph_context') or [],
        'usage': result.get('usage') or {},
        'trace': result.get('trace') or [],
        'source_binding': result.get('source_binding') or {},
    }


async def _search_with_lifecycle(backend, payload, request):
    task = asyncio.create_task(backend.search(
        payload.query, course_id=payload.course_id, mode=payload.mode, limit=payload.limit,
        chapter_id=payload.chapter_id, section_id=payload.section_id))
    try:
        # 预算限制整段查询；断连即取消，finally 兜住异常与取消的清理。
        async with asyncio.timeout(QUERY_BUDGET_SECONDS):
            while not task.done():
                if request is not None and await request.is_disconnected():
                    raise asyncio.CancelledError()
                await asyncio.wait({task}, timeout=.25)
        return await task
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def _run_search(payload, request):
    from knowledge.fixed_book import active

    started = time.perf_counter()
    fixed = active()
    if fixed is None or getattr(fixed, 'backend', None) is None:
        raise HTTPException(503, detail={'code': 'retrieval_not_ready', 'message': '教材检索尚未就绪'})
    try:
        result = await _search_with_lifecycle(fixed.backend, payload, request)
    except asyncio.CancelledError:
        raise
    except TimeoutError as exc:
        raise HTTPException(504, detail={'code': 'retrieval_timeout', 'message': '教材检索超时'}) from exc
    except PermissionError as exc:
        raise HTTPException(403, detail={'code': 'not_authorized', 'message': str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(422, detail={'code': 'invalid_query', 'message': str(exc)}) from exc
    except RuntimeError as exc:
        logging.getLogger(__name__).warning('宿主课程查询未就绪: %s', exc)
        raise HTTPException(503, detail={'code': 'retrieval_not_ready', 'message': str(exc)}) from exc
    queried = time.perf_counter()
    projected = project(result)
    projected['usage'] = {**(projected['usage'] or {}), 'stages': [
        *(projected['usage'] or {}).get('stages', []),
        {'stage': 'host.backend', 'seconds': queried - started, 'includes_children': True},
        {'stage': 'host.total', 'seconds': queried - started, 'includes_children': True},
    ]}
    logging.getLogger(__name__).info('course_search_timing %s', json.dumps({
        'request_id': payload.request_id,
        'query_hash': hashlib.sha256(payload.query.encode()).hexdigest()[:16],
        'stages': projected['usage']['stages']}, ensure_ascii=False))
    return projected


@router.post('/course-search')
async def course_search(payload: CourseSearchRequest, request: Request):
    from .native_authorization import authorize_native_task

    await asyncio.to_thread(authorize_native_task, payload)
    result = await _run_search(payload, request)
    await asyncio.to_thread(authorize_native_task, payload)
    return result


def _native_policy(user_id, is_admin):
    from deeptutor.multi_user.learning_access import learning_policy_for_user

    policy = learning_policy_for_user(user_id, is_admin=is_admin)
    if policy is not None and 'chat' not in set(policy.get('allowed_surfaces') or ['chat', 'reading']):
        raise HTTPException(403, detail={'code': 'not_authorized', 'message': '该账号不能使用聊天检索'})
    reading = (policy or {}).get('reading') if policy is not None else None
    if not isinstance(reading, dict):
        return None
    assigned = set(reading.get('material_ids') or [])
    return None if '*' in assigned else assigned


async def _native_scope(payload):
    """Bind the authenticated native user, workspace and live session."""
    from deeptutor.multi_user.identity import get_user_by_id
    from deeptutor.multi_user.models import CurrentUser, UserScope
    from deeptutor.multi_user.paths import scope_for_user, user_context
    from deeptutor.services.session import get_session_store
    from deeptutor.services.workspace.context import workspace_context
    from deeptutor.services.workspace.models import WorkspaceError

    record = get_user_by_id(payload.student_id)
    if record is None or record[0] != payload.username:
        raise HTTPException(403, detail={'code': 'not_authorized', 'message': '原生账户不存在或身份不匹配'})
    username, user = record
    if user.get('disabled'):
        raise HTTPException(403, detail={'code': 'not_authorized', 'message': '原生账户已停用'})
    role = str(user.get('role') or 'user')
    is_admin = role == 'admin'
    allowed = _native_policy(payload.student_id, is_admin)
    root = scope_for_user(payload.student_id, is_admin=is_admin).root
    current = CurrentUser(payload.student_id, username, role,
                          UserScope('admin' if is_admin else 'user', payload.student_id, root))
    try:
        with user_context(current), workspace_context(payload.workspace_id or None):
            store = get_session_store()
            session = await store.get_session(payload.session_id)
            active_turn = await store.get_active_turn(payload.session_id)
    except WorkspaceError as exc:
        raise HTTPException(409, detail={'code': 'workspace_changed', 'message': str(exc)}) from exc
    return allowed, session, active_turn


@router.post('/course-search-native')
async def course_search_native(payload: NativeUserCourseSearchRequest, request: Request):
    """原生登录用户：用户/工作区/会话/活跃回合/授权材料全部核验后才检索。"""
    from knowledge.course_config import COURSE_ID

    if payload.course_id != COURSE_ID:
        raise HTTPException(409, detail={'code': 'course_mismatch', 'message': '宿主课程不匹配'})
    allowed, session, active_turn = await _native_scope(payload)
    if session is None or active_turn is None:
        raise HTTPException(409, detail={'code': 'turn_expired', 'message': '原生会话或回合已失效'})
    if str((session.get('preferences') or {}).get('workspace_id') or '') != payload.workspace_id:
        raise HTTPException(409, detail={'code': 'workspace_changed', 'message': '原生会话工作区已变化'})
    result = await _run_search(payload, request)
    raw_sources = result.get('sources') or []
    if allowed is not None:
        sources = [source for source in raw_sources
                   if str(source.get('version') or '')[:16] in allowed]
        if raw_sources and not sources:
            raise HTTPException(403, detail={'code': 'not_authorized', 'message': '教材原文超出当前账号授权范围'})
        result = {**result, 'sources': sources}
    return result
