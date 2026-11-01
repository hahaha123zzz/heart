"""接原生应用层与持久化回合；不调用旧教学链，不将原生草稿当正式答案。"""
from contextlib import aclosing, contextmanager
import asyncio
import hashlib
import json
import os
import secrets
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from starlette.responses import StreamingResponse

from .generation_bridge import GenerationRequest, model_config
from .native_contract import NativeTurnKey, NativeTurnStart, NativeTurnCursor, NativeTurnCommand, NativeTurnReply, NativeTaskCheck
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
            db.execute('BEGIN IMMEDIATE')
            if 'teaching_style' not in {row[1] for row in db.execute('PRAGMA table_info(native_requests)')}:
                db.execute("ALTER TABLE native_requests ADD COLUMN teaching_style TEXT NOT NULL DEFAULT '{}'")
            if os.getenv('DEEPTUTOR_NATIVE_ENABLED', '0') == '1':
                from .learning_tool_adapter import install_learning_tool_factory
                install_learning_tool_factory(row[0] for row in db.execute('SELECT DISTINCT user_id FROM native_courses'))

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
        from .learning_tool_adapter import learning_tool_scope
        from .teaching_prompt_adapter import teaching_prompt_scope

        try:
            with (self.user_scope(entry['user_id']), workspace_context(entry['workspace_id']),
                  learning_tool_scope(entry), teaching_prompt_scope(entry)):
                yield DeepTutorApp(workspace_id=entry['workspace_id'])
        except WorkspaceError as exc:
            raise HTTPException(409, '原生工作区已不可用') from exc

    def account_identity(self, request):
        from deeptutor.multi_user.identity import get_user, save_user, set_role
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
        return {'user_id': user_id}

    def account(self, request, config):
        from deeptutor.multi_user.grants import empty_grant, load_grant, save_grant
        from deeptutor.multi_user.model_access import admin_catalog_service

        binding = self.account_identity(request)
        user_id = binding['user_id']
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

    async def bind_scope(self, request):
        """仅初始化服务端账户/工作区/会话，不读取模型配置或启动回合。"""
        async with self.sessions.lock:
            with self.sessions._connect() as db:
                db.execute('BEGIN IMMEDIATE')
                # 同一候选home的初始化连同账户登记一起串行，不只保护课程映射。
                binding = self.account_identity(request)
                return await self._bind(request, binding, db)

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

        await self.authorize_host(request)
        # 缺省新字段不改变旧回合的幂等收据。
        request_digest = digest(request.model_dump(exclude={'teaching_preferences'} if request.teaching_preferences is None else set()))
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
                from .teaching_prompt_adapter import teaching_snapshot
                style = teaching_snapshot(request.content, request.teaching_preferences.model_dump(exclude_none=True)
                                          if request.teaching_preferences else None,identity=request)
                db.execute('''INSERT OR IGNORE INTO native_requests
                    (student_id, course_id, session_id, request_id, task_id, task_revision, digest,
                     user_id, workspace_id, native_course_id, native_session_id, submission_id,
                     turn_id, memory_epoch, material_versions, teaching_style) VALUES
                    (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)''',
                    (*self._key(request), request.task_id, request.task_revision, request_digest,
                     mapped['user_id'], mapped['workspace_id'], mapped['native_course_id'], mapped['native_session_id'],
                     submission_id, request.memory_epoch, json.dumps(request.material_versions, sort_keys=True),
                     json.dumps(style, ensure_ascii=False, sort_keys=True)))
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

    async def authorize_host(self, request, entry=None):
        from .client import BackendUnavailable, DeepTutorBackend

        expected = NativeTaskCheck(**{
            **request.model_dump(include=set(NativeTurnKey.model_fields)),
            'memory_epoch': entry['memory_epoch'] if entry else request.memory_epoch,
            'material_versions': json.loads(entry['material_versions']) if entry else request.material_versions,
        }).model_dump()
        try:
            backend = DeepTutorBackend(base_url=os.getenv('DEEPTUTOR_HOST_URL', 'http://127.0.0.1:8000'))
            await asyncio.to_thread(backend.authorize_native_task, expected)
        except (BackendUnavailable, ValueError) as exc:
            raise HTTPException(503, '宿主任务核验未通过，原生回合不可继续') from exc

    @contextmanager
    def learning_service(self, request):
        """宿主受控学习命令入口；mastery服务工厂使用同一授权存储。"""
        from .assessment_store import HostAssessmentStore, HostAssessmentService

        entry = self.entry(request)
        check = NativeTaskCheck(**{**request.model_dump(include=set(NativeTurnKey.model_fields)),
            'memory_epoch': entry['memory_epoch'], 'material_versions': json.loads(entry['material_versions'])})
        with self.scope(entry):
            yield HostAssessmentService(HostAssessmentStore(check))

    async def authorize_assessment(self, request, entry):
        from .client import DeepTutorBackend, BackendUnavailable
        check = NativeTaskCheck(**{**request.model_dump(include=set(NativeTurnKey.model_fields)),
            'memory_epoch': entry['memory_epoch'], 'material_versions': json.loads(entry['material_versions'])})
        try:
            backend = DeepTutorBackend(base_url=os.getenv('DEEPTUTOR_HOST_URL', 'http://127.0.0.1:8000'))
            await asyncio.to_thread(backend.authorize_native_assessment, check.model_dump())
        except (BackendUnavailable, ValueError) as exc:
            if isinstance(exc, ValueError) or getattr(exc.__cause__, 'code', None) in (400, 401, 403, 404, 409, 410, 422):
                raise HTTPException(409, '已保存测评身份核验未通过') from exc
            # 超时不能证明身份失效；保留原命令 ID，允许丢响应后的幂等恢复。
            raise HTTPException(503, '测评身份暂未确认，请使用原命令重试') from exc

    async def status(self, request: NativeTurnKey):
        entry = self.entry(request)
        await self.authorize_host(request, entry)
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
        await self.authorize_host(request, entry)
        if not entry['turn_id']: raise HTTPException(409, '原生回合尚未登记完成')
        with self.scope(entry) as app:
            async with aclosing(app.stream_turn(entry['turn_id'], after_seq=request.after_seq)) as stream:
                async for event in stream:
                    if event.get('type') == 'done':
                        await self.authorize_host(request, entry)
                    yield {'engine': 'deeptutor_app', 'publication_state': 'pending_verification', 'event': event}
        await self.authorize_host(request, entry)

    async def command(self, request):
        entry = self.entry(request)
        if isinstance(request, NativeTurnReply):
            await self.authorize_host(request, entry)
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
    from .assessment_api import install_assessment_api
    install_assessment_api(router, bridge)

    @router.post('/events')
    async def events(payload: NativeTurnCursor):
        if not (await bridge.status(payload)).get('turn_id'):
            raise HTTPException(409, '原生回合尚未登记完成')
        async def frames():
            async with aclosing(bridge.events(payload)) as stream:
                async for item in stream:
                    yield json.dumps(item, ensure_ascii=False) + '\n'
        return StreamingResponse(frames(), media_type='application/x-ndjson')

    @router.post('/cancel')
    async def cancel(payload: NativeTurnCommand): return await bridge.command(payload)

    @router.post('/reply')
    async def reply(payload: NativeTurnReply): return await bridge.command(payload)

    app.include_router(router)
    return bridge
