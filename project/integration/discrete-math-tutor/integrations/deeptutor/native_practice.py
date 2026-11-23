"""只适配账号与HTTP传输；题库、判定、复习调度及导入均执行原生router。"""
import base64
from urllib.parse import parse_qsl, urlencode, urlsplit

from fastapi import FastAPI, HTTPException
import httpx
from pydantic import Field
from typing import Literal

from .native_contract import NativeScopeRequest, NativeTurnKey

MAX_BODY = 6 * 1024 * 1024

class NativePracticeRequest(NativeScopeRequest):
    method: Literal['GET', 'POST', 'PATCH', 'DELETE'] = 'GET'
    path: str = Field(min_length=1, max_length=4096)
    body: str = Field(default='', max_length=8 * 1024 * 1024)
    content_type: str = Field(default='', max_length=200)

async def dispatch(bridge, request: NativePracticeRequest):
    from deeptutor.api.routers import practice, question_notebook
    from deeptutor.services.workspace.context import workspace_context
    url = urlsplit(request.path)
    if url.scheme or url.netloc or url.fragment or not url.path.startswith('/api/question-notebook/') or '..' in url.path or '%' in url.path:
        raise HTTPException(422, '无效练习接口')
    try:
        body = base64.b64decode(request.body, validate=True)
    except ValueError as exc:
        raise HTTPException(422, '无效练习请求') from exc
    if len(body) > MAX_BODY:
        raise HTTPException(413, '练习文件过大')
    mapped = await bridge.bind_scope(request)
    query = []
    for key, value in parse_qsl(url.query, keep_blank_values=True):
        if key in {'workspace', 'dt_workspace', 'all_workspaces'}:
            continue
        if key == 'course_id' and value:
            value = mapped['native_course_id']
        query.append((key, value))
    # 不装载上游整站的登录中间件；外层bridge验证凭据，作用域始终来自宿主映射。
    app = FastAPI()
    app.include_router(question_notebook.router, prefix='/api/question-notebook')
    app.include_router(practice.router, prefix='/api/question-notebook/practice')
    with bridge.user_scope(mapped['user_id']), workspace_context(mapped['workspace_id']):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://native.local') as client:
            response = await client.request(request.method, url.path + '?' + urlencode(query),
                content=body, headers={'Content-Type': request.content_type} if request.content_type else {})
    return {'status': response.status_code, 'body': base64.b64encode(response.content).decode(),
            'headers': {key: value for key, value in response.headers.items()
                        if key in {'content-type', 'content-disposition'}}}


def install(router, bridge):
    @router.post('/practice/save-generated')
    async def save(payload: SaveGeneratedQuestion):
        return await save_generated(bridge, payload)

    @router.post('/practice')
    async def practice(payload: NativePracticeRequest):
        return await dispatch(bridge, payload)


class SaveGeneratedQuestion(NativeTurnKey):
    question_id: str = Field(min_length=1, max_length=200)

async def save_generated(bridge, request: SaveGeneratedQuestion):
    from deeptutor.api.routers.question_notebook import UpsertEntryRequest, upsert_single_entry
    entry = bridge.entry(request)
    await bridge.authorize_assessment(request, entry)
    with bridge.scope(entry) as app:
        store = app.container.store_provider.get()
        turn = await store.get_turn(entry['turn_id'])
        if not turn or turn['status'] != 'completed' or turn['capability'] != 'deep_question':
            raise HTTPException(409, '该回合没有可保存的已交付题目')
        events = await store.get_turn_events(entry['turn_id'])
        result = next((event.get('metadata') or {} for event in reversed(events) if event.get('type') == 'result'), {})
        from .native_delivery import public_quiz
        public_quiz(result)
        qa = next((row.get('qa_pair') for row in result['summary']['results']
                   if (row.get('qa_pair') or {}).get('question_id') == request.question_id), None)
        if qa is None:
            raise HTTPException(404, '该题不属于这个回合')
        fields = {key:value for key,value in qa.items() if key in UpsertEntryRequest.model_fields}
        # 答案只从已核验回合读取，不能由页面提交或覆盖。
        payload = UpsertEntryRequest(**{**fields, 'session_id': entry['native_session_id'],
            'turn_id': entry['turn_id'], 'origin_type': 'conversation',
            'origin_ref': entry['native_session_id'], 'source': 'deep_question'})
        from deeptutor.services.session import get_sqlite_session_store
        existing = await get_sqlite_session_store().find_notebook_entry_by_origin(
            payload.origin_type, payload.origin_ref, payload.question_id, turn_id=payload.turn_id)
        # 重新保存题目不能用初始空答案覆盖已经作答/复习的记录。
        if existing is not None:
            return {'id': existing['id'], 'question_id': request.question_id}
        item = await upsert_single_entry(payload)
        return {'id': item['id'], 'question_id': request.question_id}
