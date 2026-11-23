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

from .native_contract import CourseSearchRequest
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


@router.post('/course-search')
async def course_search(payload: CourseSearchRequest, request: Request):
    from knowledge.fixed_book import active
    from .native_authorization import authorize_native_task

    started = time.perf_counter()
    await asyncio.to_thread(authorize_native_task, payload)
    authorized = time.perf_counter()
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
    await asyncio.to_thread(authorize_native_task, payload)
    finished = time.perf_counter()
    projected = project(result)
    stages = [
        {'stage': 'host.authorization.before', 'seconds': authorized - started, 'includes_children': False},
        {'stage': 'host.backend', 'seconds': queried - authorized, 'includes_children': True},
        {'stage': 'host.authorization.after', 'seconds': finished - queried, 'includes_children': False},
        {'stage': 'host.total', 'seconds': finished - started, 'includes_children': True},
    ]
    usage = projected['usage']
    projected['usage'] = {**usage, 'stages': [*(usage.get('stages') or []), *stages]}
    logging.getLogger(__name__).info('course_search_timing %s', json.dumps({
        'request_id': payload.request_id, 'task_id': payload.task_id,
        'query_hash': hashlib.sha256(payload.query.encode()).hexdigest()[:16],
        'stages': projected['usage']['stages']}, ensure_ascii=False))
    return projected
