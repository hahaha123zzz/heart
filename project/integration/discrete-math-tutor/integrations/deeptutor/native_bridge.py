"""接原生应用层与持久化回合；不调用旧教学链，不将原生草稿当正式答案。"""
from contextlib import aclosing, contextmanager
import asyncio
import base64
import hashlib
import json
import logging
import os
import secrets
import sqlite3
import time

from fastapi import APIRouter, Depends, HTTPException
from starlette.responses import StreamingResponse

from .generation_bridge import GenerationRequest, model_config
from .native_contract import NativeTurnKey, NativeTurnStart, NativeTurnCursor, NativeTurnCommand, NativeTurnReply, NativeTaskCheck, NativeTurnOptions, NativeScopeRequest, NativeMemoryRequest
from .session_bridge import require_bridge_token


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def normalize_turn_options(options):
    """把旧课程库名与产品别名归一为唯一课程KB；其他KB保持原顺序。"""
    from .course_rag_provider import canonical_names
    from .product_surface import validate_options
    validate_options(options)
    names = options.get('knowledge_bases')
    if names:
        options['knowledge_bases'] = canonical_names(names)
    return options


# 宿主课程约定会注入每个原生回合的系统提示；引用编号与图表索引都在这里恢复。
COURSE_INSTRUCTIONS = (
    '教材正式答案须经宿主原文、版本与引用核验。'
    '本轮已有经核验的教材原文（包括预检索上下文）足以回答时，直接引用作答；不要仅为扩充答案或重复确认而补查。'
    '当前证据不足或相互矛盾，或本轮要求比较、推导、步骤、研究时，继续按需检索和补读；证据仍不足则使用 ask_user 澄清。'
    '使用教材内容时，必须在相应句子后写检索工具返回的短 ID（如 [S1]，多个写作 [S1, S2]），不得只用“第x章第x节”代替；系统会把短 ID 换成本轮已核验的教材链接。'
    '每轮教材问答必须先检查 lookup_figures 图表索引（预检索已查过则不重复）。'
    '有直接相关、已核对且带asset_id的原图必须调用 rag(asset_id=...) 读取并展示；无相关原图则不取图、不编造。'
    '如果检索原文或你的回答提到“图x-y/表x-y”，必须读取并至少展示一次该原图。'
    '正文只用 ![图题](media:资源ID) 展示已读取的原图。'
    '在chat模式回答学习计划请求时，确认必要偏好后，最终回复直接写出学习目标、重点和按时间安排的步骤。'
    '此课程约定不改变各原生能力的职责；course_study仍只承担课程导航和交接，不承担教学或完整计划。'
    '最终回复只保留完整交付正文，不重复工具调用前言、检索过程或等待确认前的文字。'
    '续问引用历史教材依据时须重新检索并核对当前编号，不得直接沿用历史轮次的数字引用。'

)


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
            if os.getenv('DEEPTUTOR_NATIVE_ENABLED', '1') == '1':
                from .native_history import install_question_history
                install_question_history()
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
        from .tool_policy import teaching_tool_scope

        try:
            with (self.user_scope(entry['user_id']), workspace_context(entry['workspace_id']),
                  learning_tool_scope(entry),
                  teaching_tool_scope(json.loads(entry.get('teaching_style') or '{}').get('citation_offset', 0))):
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
        current = catalog.load()
        existing = next((item for item in (current.get('services', {}).get('llm', {}) or {}).get('profiles', [])
                         if item.get('id') == profile_id), None)
        if not (existing and all(existing.get(key) == profile.get(key) for key in (
                'id', 'name', 'binding', 'base_url', 'api_key', 'wire_api', 'models'))):
            # Windows 下目标文件被并发读取时 os.replace 会短暂拒绝访问；配置未变时不再重写。
            for attempt in range(3):
                try:
                    catalog.update(update)
                    break
                except PermissionError:
                    if attempt == 2:
                        raise
                    time.sleep(0.05)
        grant = load_grant(user_id) or empty_grant(user_id)
        models = grant.setdefault('models', {}).setdefault('llm', [])
        models[:] = [item for item in models if item.get('profile_id') != profile_id] + [
            {'profile_id': profile_id, 'model_ids': ['host-model']}]
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
        from deeptutor.services.courses import CourseService, CourseNotFoundError
        from deeptutor.services.session import get_session_store
        from deeptutor.services.workspace import get_content_workspace_service
        from deeptutor.services.workspace.context import workspace_context

        with self.user_scope(binding['user_id']):
            row = db.execute('SELECT workspace_id, native_course_id FROM native_courses WHERE user_id=? AND course_id=?',
                (binding['user_id'], request.course_id)).fetchone()
            name = request.course_title[:40] + ' · native-' + digest(request.course_id)[:16]
            if row:
                workspace_id, course_id = row
                with workspace_context(workspace_id):
                    courses = CourseService()
                    try:
                        course = courses.get(course_id)
                    except CourseNotFoundError:
                        course = None
                    if course is None:
                        course = courses.create(name=name, instructions=COURSE_INSTRUCTIONS,
                                                default_capability='chat')
                        from .course_study import ensure_syllabus
                        ensure_syllabus(course.id)
                        db.execute('UPDATE native_courses SET native_course_id=? WHERE user_id=? AND course_id=?',
                            (course.id, binding['user_id'], request.course_id))
                    elif course.instructions != COURSE_INSTRUCTIONS:
                        courses.update(course.id, instructions=COURSE_INSTRUCTIONS)
                    course_id = course.id
            else:
                service = get_content_workspace_service()
                workspace = next((item for item in service.list_workspaces()
                    if item['kind'] == 'workspace' and item['display_name'] == name), None)
                if workspace is None:
                    workspace = service.create_workspace(name, resources={})
                workspace_id = workspace['workspace_id']
                with workspace_context(workspace_id):
                    courses = CourseService()
                    course = next((item for item in courses.list_courses() if item.name == name), None)
                    if course is None:
                        course = courses.create(name=name, instructions=COURSE_INSTRUCTIONS, default_capability='chat')
                    elif course.instructions != COURSE_INSTRUCTIONS:
                        courses.update(course.id, instructions=COURSE_INSTRUCTIONS)
                    course_id = course.id
                    from .course_study import ensure_syllabus
                    ensure_syllabus(course_id)
                db.execute('INSERT INTO native_courses VALUES (?, ?, ?, ?)',
                    (binding['user_id'], request.course_id, workspace_id, course_id))
            session_digest = digest([binding['user_id'], request.course_id, request.session_id])
            session_id = 'heart_native_' + session_digest
            with workspace_context(workspace_id):
                from .course_rag_provider import register_course_sources
                register_course_sources(course_id)
                store = get_session_store()
                imported = 'imported_heart_' + session_digest
                if await store.get_session(imported) is not None:
                    session_id = imported
                if await store.get_session(session_id) is None:
                    await store.create_session(title=request.course_title, session_id=session_id)
                session = await store.get_session(session_id)
                current = (session or {}).get('preferences') or {}
                update = {}
                if current.get('course_id') != course_id or current.get('heart_native') is not True:
                    update.update({'course_id': course_id, 'heart_native': True})
                names = current.get('knowledge_bases')
                if names:
                    normalized = normalize_turn_options({'knowledge_bases': names})['knowledge_bases']
                    if normalized != list(names):
                        update['knowledge_bases'] = normalized
                if update:
                    await store.update_session_preferences(session_id, update)
            return {'user_id': binding['user_id'], 'workspace_id': workspace_id,
                'native_course_id': course_id, 'native_session_id': session_id}

    async def ui_settings(self, request: NativeScopeRequest):
        from deeptutor.api.routers.settings import get_ui_settings
        from deeptutor.services.workspace.context import workspace_context
        mapped = await self.bind_scope(request)
        with self.user_scope(mapped['user_id']), workspace_context(mapped['workspace_id']):
            return await get_ui_settings()

    async def memory(self, request: NativeMemoryRequest):
        from deeptutor.api.routers import memory as native_memory
        from deeptutor.services.workspace.context import workspace_context
        mapped = await self.bind_scope(request)
        with self.user_scope(mapped['user_id']), workspace_context(mapped['workspace_id']):
            if request.action == 'overview':
                from deeptutor.api.routers.learning_journal import overview
                result = await native_memory.get_overview()
                result['learning_journal'] = overview()
                return result
            if request.action == 'read':
                return await native_memory.get_doc(request.layer, request.key)
            if request.action == 'write':
                return await native_memory.put_doc(request.layer, request.key,
                    native_memory.DocWriteRequest(content=request.content))
            if request.action == 'entries':
                return await native_memory.get_doc_lines(request.layer, request.key)
            return await native_memory.delete_entry(request.layer, request.key, request.entry_id)

    async def catalog(self, request: NativeScopeRequest):
        from deeptutor.app import DeepTutorApp
        from deeptutor.capabilities.registry import BUILTIN_LOOP_CAPABILITY_SPECS
        from deeptutor.tools.builtin_specs import BUILTIN_TOOL_SPECS
        from deeptutor.tools.builtin import USER_TOGGLEABLE_TOOL_NAMES, CONFIGURABLE_BUILTIN_TOOL_NAMES
        from deeptutor.services.workspace.context import workspace_context
        from deeptutor.services.workspace.resources import current_resources, resource_catalog
        from deeptutor.multi_user.grants import load_grant
        from .tool_policy import visible, hidden_names, HIDDEN_EXTENSIONS
        mapped = await self.bind_scope(request)
        from .tool_policy import teaching_tool_scope
        from .product_surface import CHAT_CAPABILITIES
        with self.user_scope(mapped['user_id']), workspace_context(mapped['workspace_id']), teaching_tool_scope():
            app = DeepTutorApp(workspace_id=mapped['workspace_id'])
            resources = current_resources()
            grant = load_grant(mapped['user_id'])
            allowed = grant.get('enabled_tools')
            # 工作区限制为 None 表示不限制；只展示用户确实可用的资源。
            options = {kind: [item for item in values
                              if getattr(resources, kind, None) is None
                              or item['id'] in (getattr(resources, kind) or ())]
                       for kind, values in resource_catalog(workspace_id=mapped['workspace_id']).items()}
            from deeptutor.services.persona import get_persona_service
            personas = [item.to_dict() for item in get_persona_service().list_personas()]
            manifests = app.capabilities.get_manifests()
            return {
                'engine': 'deeptutor_app', 'personas': personas,
                # 固定上游 availability 是 slots dataclass，不能读取 __dict__。
                'capabilities': [{**manifest, 'availability': __import__('dataclasses').asdict(
                    app.get_capability_availability(manifest['name'], manifests=manifests))}
                    for manifest in manifests if manifest['name'] in CHAT_CAPABILITIES],
                'tools': [{'name': spec.name, 'class_path': spec.class_path, 'registered': True,
                    'user_toggleable': spec.name in USER_TOGGLEABLE_TOOL_NAMES,
                    'context_gated': spec.name in CONFIGURABLE_BUILTIN_TOOL_NAMES,
                    'allowed_by_grant': allowed is None or spec.name in allowed,
                    'execution_verified': False} for spec in BUILTIN_TOOL_SPECS if visible(spec.name)],
                'hidden_tool_count': len(hidden_names()),
                'extensions': [{'name': spec.name, 'class_path': spec.class_path,
                                'registered': True, 'execution_verified': False}
                               for spec in BUILTIN_LOOP_CAPABILITY_SPECS if spec.name not in HIDDEN_EXTENSIONS],
                'hidden_extension_count': len(HIDDEN_EXTENSIONS),
                'resources': {**{key: [item['id'] for item in options.get(key, [])]
                              for key in ('knowledge_bases', 'skills', 'mcp')},
                              'memory_references': ['recent','profile','scope','preferences','summary']},
                'resource_options': {key: [{field: item[field] for field in
                                            ('id', 'name', 'description', 'available') if field in item}
                                           for item in values] for key, values in options.items()} | {
                    'memory_references': [{'id':key,'name':label,'available':True} for key,label in (
                        ('recent','近期记忆'),('profile','个人资料'),('scope','学习范围'),
                        ('preferences','长期偏好'),('summary','记忆摘要'))]},
            }

    async def prepare_reading(self, request: NativeScopeRequest):
        """导入课程教材并返回原生阅读工作区；幂等，供宿主阅读请求预取材料。"""
        from deeptutor.services.workspace.context import workspace_context
        from .course_reading import ensure_course_reading

        mapped = await self.bind_scope(request)
        with self.user_scope(mapped['user_id']), workspace_context(mapped['workspace_id']):
            return await asyncio.to_thread(ensure_course_reading)

    async def resolve_session(self, request):
        mapped=await self.bind_scope(request)
        with self.sessions._connect() as db:
            rows=db.execute("""SELECT DISTINCT session_id,task_id FROM native_requests
                WHERE student_id=? AND course_id=? AND user_id=? AND workspace_id=? AND native_session_id=?""",
                (request.student_id,request.course_id,mapped['user_id'],mapped['workspace_id'],request.native_session_id)).fetchall()
        return {'candidates':[{'session_id':row[0],'task_id':row[1]} for row in rows]}

    async def route(self, request: NativeTurnStart):
        from deeptutor.app import DeepTutorApp
        from deeptutor.services.workspace.context import workspace_context
        from deeptutor.services.llm.config import set_scoped_llm_config,reset_scoped_llm_config
        from .native_routing import choose_options
        await self.authorize_host(request)
        config=model_config(GenerationRequest(model=os.getenv('DEEPSEEK_MODEL') or os.getenv('OPENAI_MODEL','deepseek-flash'),
            messages=[{'role':'user','content':request.content}]))
        async with self.sessions.lock:
            binding,_=self.account(request,config)
            with self.sessions._connect() as db:
                mapped=await self._bind(request,binding,db)
        # 模型选择在全局登记锁之外，同一用户请求仍由宿主收据串行化。
        with self.user_scope(mapped['user_id']),workspace_context(mapped['workspace_id']):
            token=set_scoped_llm_config(config)
            try:
                return await choose_options(DeepTutorApp(workspace_id=mapped['workspace_id']),request)
            finally:
                reset_scoped_llm_config(token)

    async def start(self, request: NativeTurnStart):
        from .heart_rag import install_heart_tools
        install_heart_tools()
        from deeptutor.services.llm.config import reset_scoped_llm_config, set_scoped_llm_config
        from deeptutor.services.session.protocol import ActiveTurnConflict

        _started = time.perf_counter()
        def mark(name):
            print(f"worker_native_start {name} request={request.request_id} {time.perf_counter() - _started:.3f}", flush=True)
        await self.authorize_host(request)
        mark("authorize")
        # 缺省新字段不改变旧回合的幂等收据。
        request_digest = digest(request.receipt_payload())
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
            mark("account")
            with self.sessions._connect() as db:
                db.execute('BEGIN IMMEDIATE')
                mapped = await self._bind(request, binding, db)
                submission_id = 'heart_submission_' + digest([*self._key(request), request.task_id, request.task_revision])
                style = {'citation_offset': sum(obj.get('kind') == 'verified_evidence' for obj in request.grounding)}
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
            mark("bind")
            if entry['digest'] != request_digest: raise HTTPException(409, '请求收据发生冲突')
            if not entry['turn_id']:
                with self.scope(entry) as app:
                    store = app.container.store_provider.get()
                    # 原生 start 会重试失败的 submission，宿主普通重发必须复用失败收据。
                    turn = await store.submission_turn(submission_id)
                    if turn is None:
                        token = set_scoped_llm_config(config)
                        try:
                            options = request.model_dump(include=set(NativeTurnOptions.model_fields), exclude_unset=True)
                            normalize_turn_options(options)
                            if (request.capability == 'immersive_reading'
                                    or request.workspace_mode == 'immersive_reading'):
                                from .course_reading import ensure_course_reading, material_for_chapter
                                prepared = await asyncio.to_thread(ensure_course_reading)
                                from deeptutor.services.courses import get_course_service
                                await asyncio.to_thread(lambda: get_course_service().attach_resource(
                                    entry['native_course_id'], kind='reading_workspace',
                                    ref_id=prepared['workspace_id'], label=prepared['course_title']))
                                viewport = dict(request.reading_viewport or {})
                                chapter_id = viewport.pop('chapter_id', None)
                                document_id = viewport.pop('document_id', None)
                                legacy_selection = viewport.pop('legacy_reader_selection', None)
                                options['reading_viewport'] = viewport or None
                                options['reading_workspace_id'] = prepared['workspace_id']
                                requested_material = options.get('reading_material_id')
                                if legacy_selection or document_id is not None or chapter_id is not None:
                                    candidates = [row for row in prepared['materials']
                                        if (document_id is None or row['document_id'] == document_id)
                                        and (chapter_id is None or row['chapter_id'] == chapter_id)]
                                    if len(candidates) != 1:
                                        raise HTTPException(409, '引用对应的教材不存在或版本已变化')
                                    material = candidates[0]
                                    material_id = material['material_id']
                                    if requested_material and requested_material != material_id:
                                        raise HTTPException(409, '教材引用与当前教材不匹配')
                                    from deeptutor.reading import ReadingStore
                                    manifest = await asyncio.to_thread(ReadingStore().manifest, material_id)
                                    requested_revision = options.get('reading_material_revision')
                                    if requested_revision and requested_revision != manifest.revision:
                                        raise HTTPException(409, '教材文本版本已变化，请重新选择教材页')
                                    options['reading_material_id'] = material_id
                                    options['reading_material_revision'] = manifest.revision
                                    if legacy_selection:
                                        from knowledge.pdf_reader import PDFSelection, resolve_selection, evidence_text
                                        if not isinstance(legacy_selection, dict):
                                            raise HTTPException(400, '教材选区格式无效')
                                        if (legacy_selection.get('document_id') != material['document_id']
                                                or legacy_selection.get('version') != material['version']):
                                            raise HTTPException(409, '选区对应的教材版本已变化，请重新选择')
                                        try:
                                            selection = PDFSelection.model_validate({
                                                'document_id': legacy_selection.get('document_id'),
                                                'version': legacy_selection.get('version'),
                                                'kind': legacy_selection.get('kind'),
                                                'rects': legacy_selection.get('rects'),
                                                'text': '',
                                            })
                                            resolved = await asyncio.to_thread(resolve_selection, selection)
                                        except (ValueError, TypeError) as exc:
                                            raise HTTPException(400, str(exc) or '教材选区已失效，请重新选择') from None
                                        if resolved['reference']['chapter_id'] != material['chapter_id']:
                                            raise HTTPException(409, '选区对应的章节已变化，请重新选择')
                                        pages = sorted({rect.page for rect in selection.rects})
                                        if len(pages) > 40:
                                            raise HTTPException(400, '一次最多引用 40 页，请缩小选区')
                                        viewport['locator'] = pages[0]
                                        viewport['selection'] = resolved['text']
                                        viewport['selection_pages'] = []
                                        for page in pages:
                                            page_rects = [rect for rect in selection.rects if rect.page == page]
                                            page_text = await asyncio.to_thread(
                                                evidence_text, selection.document_id, selection.version, page_rects)
                                            viewport['selection_pages'].append({
                                                'locator': page,
                                                'quote': page_text[:2000],
                                                'rects': [[rect.x1, rect.y1, rect.x2, rect.y2] for rect in page_rects],
                                            })
                                        if selection.kind == 'area':
                                            expected_filename = str(legacy_selection.get('attachment_filename') or '')
                                            verified_images = resolved['images']
                                            if len(verified_images) != 1 or verified_images[0].name != expected_filename:
                                                raise HTTPException(409, '选区图片已变化，请重新框选')
                                            attachments = list(options.get('attachments') or [])
                                            matches = [index for index, attachment in enumerate(attachments)
                                                if isinstance(attachment, dict)
                                                and attachment.get('filename') == expected_filename
                                                and str(attachment.get('type') or '').lower() == 'image']
                                            if len(matches) != 1:
                                                raise HTTPException(409, '选区图片已移除，请重新框选')
                                            image_bytes = await asyncio.to_thread(verified_images[0].read_bytes)
                                            attachments[matches[0]] = {
                                                'type': 'image', 'filename': expected_filename,
                                                'base64': base64.b64encode(image_bytes).decode('ascii'),
                                                'mime_type': 'image/png',
                                            }
                                            options['attachments'] = attachments
                                else:
                                    options['reading_material_id'] = requested_material or \
                                        material_for_chapter(prepared)
                                    options['reading_material_revision'] = options.get('reading_material_revision') or 1
                            if request.grounding:
                                notebook_name = 'Heart 本轮材料 · ' + submission_id
                                notebook = next((item for item in app.list_notebooks()
                                                 if item['name'] == notebook_name), None)
                                if notebook is None:
                                    notebook = app.create_notebook(notebook_name, description='宿主校验后的本轮材料，非模型生成')
                                    for obj in request.grounding:
                                        app.add_record(notebook_ids=[notebook['id']], record_type='reading',
                                            title=obj['title'], user_query=request.content, output=obj['text'],
                                            metadata={'host_object': obj, 'material_versions': request.material_versions})
                                options['notebook_references'] = [*options.get('notebook_references', []),
                                    {'notebook_id': notebook['id'], 'record_ids': []}]
                            from .tool_policy import install_tool_policy
                            install_tool_policy()
                            _, turn = await app.start_turn({**options, 'content': request.content,
                                'capability': request.capability, 'session_id': entry['native_session_id'],
                                'workspace_id': entry['workspace_id'], 'course_id': entry['native_course_id'],
                                'client_submission_id': submission_id, 'language': 'zh',
                                'llm_selection': selection})
                            mark("start_turn")
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
        mark("before_status")
        result = await self.status(request)
        mark("status")
        return result

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
            output = {}
            if turn['status'] in ('completed', 'failed', 'cancelled'):
                messages = await store.get_messages(entry['native_session_id'])
                message = next((m for m in messages if str(m.get('id')) == str(turn.get('assistant_message_id'))), None)
                output['reply'] = str(message.get('content') or '') if message else ''
                events = await store.get_turn_events(entry['turn_id'])
                result = next((e.get('metadata') or {} for e in reversed(events) if e.get('type') == 'result'), {})
                from .native_reader import reader_actions
                output['reader_actions'] = await asyncio.to_thread(reader_actions, events) if turn['status'] == 'completed' else []
                from .native_delivery import public_mastery_events
                output['mastery_events'] = public_mastery_events(events)
                output['result'] = result
                output['sources'] = [s for e in events if e.get('type') == 'sources'
                                     for s in (e.get('metadata') or {}).get('sources', [])]
            return {**output, 'engine': 'deeptutor_app', 'turn_id': turn['id'], 'session_id': entry['native_session_id'],
                'workspace_id': entry['workspace_id'], 'capability': turn['capability'],
                'status': turn['status'], 'last_seq': turn['last_seq'],
                'publication_state': 'pending_verification'}

    async def artifact(self, request):
        from fastapi.responses import FileResponse
        from deeptutor.services.workspace import get_content_workspace_service
        entry = self.entry(request)
        await self.authorize_assessment(request, entry)
        with self.scope(entry) as app:
            events = await app.container.store_provider.get().get_turn_events(entry['turn_id'])
            items = [item for e in events if e.get('type') == 'sources'
                     for item in (e.get('metadata') or {}).get('sources', []) if item.get('type') == 'workspace_item']
            items += [item for e in events if e.get('type') == 'result'
                      for item in (e.get('metadata') or {}).get('workspace_items', [])]
            if not any(item.get('workspace_item_id') == request.item_id
                       and item.get('workspace_id') == entry['workspace_id'] for item in items):
                raise HTTPException(404, '文件不属于当前原生回合')
            path, item = get_content_workspace_service().resolve_published_item(entry['workspace_id'], request.item_id)
            return FileResponse(path, media_type=item.mime_type, filename=item.filename,
                headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'private, no-store',
                    'Content-Security-Policy': "sandbox; default-src 'none'; img-src data: blob:; media-src 'self' blob:; style-src 'unsafe-inline'"})

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
    if os.getenv('DEEPTUTOR_NATIVE_ENABLED', '1') != '1':
        raise HTTPException(503, '完整原生运行时尚未开放')


def install_native_bridge(app, sessions):
    bridge = NativeTurnBridge(sessions)
    router = APIRouter(prefix='/internal/heart/native', dependencies=[Depends(require_bridge_token), Depends(require_native_enabled)])
    router.add_api_route('/catalog', bridge.catalog, methods=['POST'], response_model=None)
    router.add_api_route('/memory', bridge.memory, methods=['POST'], response_model=None)
    router.add_api_route('/ui', bridge.ui_settings, methods=['POST'], response_model=None)
    router.add_api_route('/reading/prepare', bridge.prepare_reading, methods=['POST'], response_model=None)
    router.add_api_route('/route', bridge.route, methods=['POST'], response_model=None)
    from .native_contract import NativeSessionLookup
    @router.post('/sessions/resolve')
    async def resolve_session(payload: NativeSessionLookup): return await bridge.resolve_session(payload)

    router.add_api_route('/start', bridge.start, methods=['POST'], response_model=None)
    router.add_api_route('/status', bridge.status, methods=['POST'], response_model=None)
    from .native_contract import NativeArtifactRequest
    @router.post('/artifact')
    async def artifact(payload: NativeArtifactRequest): return await bridge.artifact(payload)

    from .native_learning_view import install as install_learning_view
    install_learning_view(router, bridge)

    from .native_learning_write import install as install_learning_write
    install_learning_write(router, bridge)

    from .legacy_migration import install as install_migration
    install_migration(router, bridge)

    from .native_practice import install as install_practice
    install_practice(router, bridge)

    # 旧测评命令已归档；新题卡使用原生LearningTurnAdapter。

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
