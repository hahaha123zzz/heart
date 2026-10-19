"""接原生应用层与持久化回合；不调用旧教学链，不将原生草稿当正式答案。"""
from contextlib import contextmanager
import hashlib
import json
import os
import secrets
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from starlette.responses import StreamingResponse

from .generation_bridge import GenerationRequest, model_config
from .native_contract import NativeTurnKey, NativeTurnStart, NativeTurnCursor, NativeTurnCommand, NativeTurnReply
from .session_bridge import require_bridge_token


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


class NativeTurnBridge:
    def __init__(self, sessions):
        self.sessions = sessions
        with sessions._connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS native_courses (
                    user_id TEXT NOT NULL, course_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL, native_course_id TEXT NOT NULL,
                    PRIMARY KEY(user_id, course_id));
                CREATE TABLE IF NOT EXISTS native_requests (
                    student_id TEXT NOT NULL, course_id TEXT NOT NULL, session_id TEXT NOT NULL,
                    request_id TEXT NOT NULL, task_id TEXT NOT NULL, task_revision INTEGER NOT NULL,
                    digest TEXT NOT NULL, user_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
                    native_course_id TEXT NOT NULL, native_session_id TEXT NOT NULL,
                    submission_id TEXT NOT NULL UNIQUE, turn_id TEXT UNIQUE,
                    memory_epoch INTEGER NOT NULL, material_versions TEXT NOT NULL,
                    PRIMARY KEY(student_id, course_id, session_id, request_id));
            ''')

    @staticmethod
    def _key(request):
        return (request.student_id, request.course_id, request.session_id, request.request_id)

    def entry(self, request):
        with self.sessions._connect() as db:
            db.row_factory = sqlite3.Row
            row = db.execute('''SELECT * FROM native_requests
                WHERE student_id=? AND course_id=? AND session_id=? AND request_id=?''', self._key(request)).fetchone()
        if row is None: raise HTTPException(404, '原生回合不存在')
        if row['task_id'] != request.task_id or row['task_revision'] != request.task_revision:
            raise HTTPException(409, '宿主任务版本与原生回合不匹配')
        return dict(row)

    @contextmanager
    def user_scope(self, user_id):
        from deeptutor.multi_user.identity import get_user_by_id
        from deeptutor.multi_user.models import CurrentUser, UserScope
        from deeptutor.multi_user.paths import scope_for_user, user_context

        record = get_user_by_id(user_id)
        root = scope_for_user(user_id, is_admin=False).root
        if not record or record[1].get('disabled') or not root.is_dir():
            raise HTTPException(404, '原生账户数据已失效')
        user = CurrentUser(user_id, record[0], 'user', UserScope('user', user_id, root))
        with user_context(user): yield

    @contextmanager
    def scope(self, entry):
        from deeptutor.app import DeepTutorApp
        from deeptutor.services.workspace.context import workspace_context
        from deeptutor.services.workspace.models import WorkspaceError

        try:
            with self.user_scope(entry['user_id']), workspace_context(entry['workspace_id']):
                yield DeepTutorApp(workspace_id=entry['workspace_id'])
        except WorkspaceError as exc:
            raise HTTPException(409, '原生工作区已不可用') from exc

    def account(self, request, config):
        from deeptutor.multi_user.identity import get_user, save_user, set_role
        from deeptutor.multi_user.grants import empty_grant, load_grant, save_grant
        from deeptutor.multi_user.model_access import admin_catalog_service
        from deeptutor.multi_user.paths import ensure_user_workspace
        from deeptutor.services.auth import hash_password

        username = 'heart_native_' + digest(request.student_id)
        record = get_user(username)
        if record is None:
            record = save_user(username, hash_password(secrets.token_urlsafe(32)), role='user')
            # 上游把首个账户自动设为 admin；桥接账户必须始终保持普通用户。
            set_role(username, 'user')
        if record.get('disabled'): raise HTTPException(409, '原生账户已停用')
        user_id = record['id']
        ensure_user_workspace(user_id)
        profile_id = 'heart-host-' + digest([config.model, config.base_url])[:24]
        profile = {'id': profile_id, 'name': 'Heart 宿主模型', 'binding': config.binding,
            'base_url': config.base_url, 'api_key': config.api_key, 'wire_api': config.wire_api,
            'models': [{'id': 'host-model', 'name': config.model, 'model': config.model}]}
        catalog = admin_catalog_service()
        def update(value):
            profiles = value['services']['llm']['profiles']
            profiles[:] = [item for item in profiles if item['id'] != profile_id] + [profile]
        catalog.update(update)
        grant = empty_grant(user_id)
        grant.update(enabled_tools=[], mcp_tools=[], cli_apps=[], exec_enabled=False)
        grant['models']['llm'] = [{'profile_id': profile_id, 'model_ids': ['host-model']}]
        if load_grant(user_id) != grant: save_grant(user_id, grant)
        return {'user_id': user_id}, {'profile_id': profile_id, 'model_id': 'host-model'}

    async def _bind(self, request, binding, db):
        from deeptutor.services.courses import CourseService
        from deeptutor.services.session import get_session_store
        from deeptutor.services.workspace import get_content_workspace_service
        from deeptutor.services.workspace.context import workspace_context

        with self.user_scope(binding['user_id']):
            row = db.execute('SELECT workspace_id, native_course_id FROM native_courses WHERE user_id=? AND course_id=?',
                (binding['user_id'], request.course_id)).fetchone()
            name = request.course_title[:40] + ' · native-' + digest(request.course_id)[:16]
            if row:
                workspace_id, course_id = row
            else:
                service = get_content_workspace_service()
                workspace = next((item for item in service.list_workspaces()
                    if item['kind'] == 'workspace' and item['display_name'] == name), None)
                if workspace is None:
                    workspace = service.create_workspace(name, resources={'skills': [], 'mcp': [], 'knowledge_bases': []})
                workspace_id = workspace['workspace_id']
                with workspace_context(workspace_id):
                    courses = CourseService()
                    course = next((item for item in courses.list_courses() if item.name == name), None)
                    if course is None:
                        course = courses.create(name=name, instructions='教材正式答案须经宿主原文、版本与引用核验。', default_capability='chat')
                    course_id = course.id
                db.execute('INSERT INTO native_courses VALUES (?, ?, ?, ?)',
                    (binding['user_id'], request.course_id, workspace_id, course_id))
            session_id = 'heart_native_' + digest([binding['user_id'], request.course_id, request.session_id])
            with workspace_context(workspace_id):
                store = get_session_store()
                if await store.get_session(session_id) is None:
                    await store.create_session(title=request.course_title, session_id=session_id)
                    await store.update_session_preferences(session_id, {'course_id': course_id, 'heart_native': True})
            return {'user_id': binding['user_id'], 'workspace_id': workspace_id,
                'native_course_id': course_id, 'native_session_id': session_id}

    async def start(self, request: NativeTurnStart):
        from deeptutor.services.llm.config import reset_scoped_llm_config, set_scoped_llm_config
        from deeptutor.services.session.protocol import ActiveTurnConflict

        request_digest = digest(request.model_dump())
        try:
            previous = self.entry(request)
        except HTTPException as exc:
            if exc.status_code != 404: raise
            previous = None
        if previous:
            if previous['digest'] != request_digest: raise HTTPException(409, '同一请求不能改变内容或资源快照')
            if previous['turn_id']: return await self.status(request)
        config = model_config(GenerationRequest(model=os.getenv('DEEPSEEK_MODEL') or os.getenv('OPENAI_MODEL', 'deepseek-flash'),
            messages=[{'role': 'user', 'content': request.content}]))
        # 只串行登记及原生 admission；模型任务和用户等待不在此锁内。
        async with self.sessions.lock:
            binding, selection = self.account(request, config)
            with self.sessions._connect() as db:
                db.execute('BEGIN IMMEDIATE')
                mapped = await self._bind(request, binding, db)
                submission_id = 'heart_submission_' + digest([*self._key(request), request.task_id, request.task_revision])
                db.execute('''INSERT OR IGNORE INTO native_requests VALUES
                    (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)''',
                    (*self._key(request), request.task_id, request.task_revision, request_digest,
                     mapped['user_id'], mapped['workspace_id'], mapped['native_course_id'], mapped['native_session_id'],
                     submission_id, request.memory_epoch, json.dumps(request.material_versions, sort_keys=True)))
            entry = self.entry(request)
            if entry['digest'] != request_digest: raise HTTPException(409, '请求收据发生冲突')
            if not entry['turn_id']:
                with self.scope(entry) as app:
                    store = app.container.store_provider.get()
                    # 原生 start 会重试失败的 submission，宿主普通重发必须复用失败收据。
                    turn = await store.submission_turn(submission_id)
                    if turn is None:
                        token = set_scoped_llm_config(config)
                        try:
                            _, turn = await app.start_turn({'content': request.content,
                                'capability': request.capability, 'session_id': entry['native_session_id'],
                                'workspace_id': entry['workspace_id'], 'course_id': entry['native_course_id'],
                                'client_submission_id': submission_id, 'language': 'zh', 'auto_route': False,
                                'llm_selection': selection,
                                'tools': [], 'knowledge_bases': []})
                        except ActiveTurnConflict as exc:
                            raise HTTPException(409, '该原生会话仍有活跃回合') from exc
                        except RuntimeError as exc:
                            # 固定上游在协调器 admission 冲突时尚未使用 ActiveTurnConflict。
                            if str(exc) == 'Session already has an active or recovering turn':
                                raise HTTPException(409, '该原生会话仍有活跃回合') from exc
                            raise
                        finally:
                            reset_scoped_llm_config(token)
                    with self.sessions._connect() as db:
                        db.execute('''UPDATE native_requests SET turn_id=?
                            WHERE student_id=? AND course_id=? AND session_id=? AND request_id=?''',
                            (turn['id'], *self._key(request)))
        return await self.status(request)

    async def status(self, request: NativeTurnKey):
        entry = self.entry(request)
        if not entry['turn_id']:
            return {'engine': 'deeptutor_app', 'status': 'admitting', 'publication_state': 'pending_verification'}
        with self.scope(entry) as app:
            store = app.container.store_provider.get()
            turn = await store.get_turn(entry['turn_id'])
            if turn is None or turn['session_id'] != entry['native_session_id']:
                raise HTTPException(409, '原生回合数据已失效')
            return {'engine': 'deeptutor_app', 'turn_id': turn['id'], 'session_id': entry['native_session_id'],
                'workspace_id': entry['workspace_id'], 'status': turn['status'], 'last_seq': turn['last_seq'],
                'publication_state': 'pending_verification'}

    async def events(self, request):
        entry = self.entry(request)
        if not entry['turn_id']: raise HTTPException(409, '原生回合尚未登记完成')
        with self.scope(entry) as app:
            async for event in app.stream_turn(entry['turn_id'], after_seq=request.after_seq):
                yield {'engine': 'deeptutor_app', 'publication_state': 'pending_verification', 'event': event}

    async def command(self, request):
        entry = self.entry(request)
        if not entry['turn_id']: raise HTTPException(409, '原生回合尚未登记完成')
        with self.scope(entry) as app:
            await app.container.start()
            if isinstance(request, NativeTurnReply):
                accepted = await app.turns.submit_user_reply(entry['turn_id'], text=request.text, command_id=request.command_id)
            else:
                accepted = await app.turns.cancel_turn(entry['turn_id'], command_id=request.command_id)
        return {'engine': 'deeptutor_app', 'command_id': request.command_id, 'accepted': accepted}


def require_native_enabled():
    if os.getenv('DEEPTUTOR_NATIVE_ENABLED', '0') != '1':
        raise HTTPException(503, '完整原生运行时尚未开放')


def install_native_bridge(app, sessions):
    bridge = NativeTurnBridge(sessions)
    router = APIRouter(prefix='/internal/heart/native', dependencies=[Depends(require_bridge_token), Depends(require_native_enabled)])
    router.add_api_route('/start', bridge.start, methods=['POST'], response_model=None)
    router.add_api_route('/status', bridge.status, methods=['POST'], response_model=None)

    @router.post('/events')
    async def events(payload: NativeTurnCursor):
        if not (await bridge.status(payload)).get('turn_id'):
            raise HTTPException(409, '原生回合尚未登记完成')
        async def frames():
            async for item in bridge.events(payload):
                yield json.dumps(item, ensure_ascii=False) + '\n'
        return StreamingResponse(frames(), media_type='application/x-ndjson')

    @router.post('/cancel')
    async def cancel(payload: NativeTurnCommand): return await bridge.command(payload)

    @router.post('/reply')
    async def reply(payload: NativeTurnReply): return await bridge.command(payload)

    app.include_router(router)
    return bridge
