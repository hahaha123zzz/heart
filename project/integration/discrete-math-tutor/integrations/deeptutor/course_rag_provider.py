"""把宿主已常驻的 LightRAG 教材库接入原生RAGService/provider与KB清单。

课程只有一个规范教材库；两个旧课程库名与产品别名只作为输入兼容别名，
执行投影统一指向宿主 LightRAG。旧注册项与索引保留，但不再被执行。
"""
import asyncio
import copy
import hashlib
import json
import logging
import os
import time
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

PROVIDER = 'heart-course-lightrag'
LEGACY_PROVIDERS = ('heart-legacy', 'heart-local-llamaindex')
DEFAULT_MODE = os.getenv('HEART_COURSE_RAG_MODE', 'naive')
if DEFAULT_MODE not in ('naive', 'local', 'global', 'hybrid', 'mix'):
    DEFAULT_MODE = 'naive'
_context = ContextVar('heart_course_retrieval_context', default=None)
ERROR_TYPES = {403: 'permission', 409: 'stale', 422: 'invalid', 503: 'not_ready', 504: 'timeout'}


def canonical_kb_name():
    from knowledge.course_config import COURSE_ID
    return COURSE_ID + '-lightrag'


def legacy_aliases():
    from knowledge.course_config import COURSE_ID
    return frozenset((COURSE_ID + '-legacy', COURSE_ID + '-local_llamaindex',
                      '课程教材', '实验心理学'))


def canonical_kb(name):
    value = str(name or '').strip()
    return canonical_kb_name() if value in legacy_aliases() else value


def canonical_names(names):
    output = []
    for name in names or []:
        canonical = canonical_kb(name)
        if canonical and canonical not in output:
            output.append(canonical)
    return output


def source_root():
    from knowledge.course_config import PSYCHOLOGY_DIR
    return PSYCHOLOGY_DIR.resolve()


def probe(provider, storage_dir):
    """目录探测只核验 LightRAG 候选结构；实际就绪仍由宿主 runtime 判定。"""
    from deeptutor.services.rag.index_probe import ProviderIndexProbe
    path = Path(storage_dir).resolve() if storage_dir else None
    if provider != PROVIDER or path != source_root():
        return ProviderIndexProbe(provider, str(path), False, '教材来源路径不匹配')
    candidate = os.getenv('LIGHTRAG_CANDIDATE_PATH')
    if not candidate:
        return ProviderIndexProbe(provider, str(path), False, 'LightRAG候选未配置')
    root = Path(candidate)
    try:
        from knowledge.course_config import COURSE_ID
        progress = json.loads((root / 'progress.json').read_text(encoding='utf-8'))
        manifest = json.loads((root / 'input_manifest.json').read_text(encoding='utf-8'))
        policy = json.loads((root / 'policy.json').read_text(encoding='utf-8'))
        index_files = json.loads((root / 'index_files.json').read_text(encoding='utf-8'))
        chapters = progress.get('chapters') or {}
        ready = (progress.get('state') == 'candidate_complete' and len(chapters) == 11
                 and all(item.get('complete') for item in chapters.values())
                 and manifest.get('course_id') == COURSE_ID and bool(manifest.get('files'))
                 and bool(policy.get('input_signature')) and bool(index_files)
                 and (root / 'index').is_dir())
        return ProviderIndexProbe(provider, str(path), ready,
            '' if ready else 'LightRAG教材索引未完整就绪', len(chapters),
            {'engine': 'lightrag', 'read_only': True, 'candidate': root.name})
    except (OSError, ValueError, AttributeError):
        return ProviderIndexProbe(provider, str(path), False, 'LightRAG候选索引不可读')


@contextmanager
def retrieval_context(context):
    token = _context.set(context if context is not None else _context.get())
    try:
        yield
    finally:
        _context.reset(token)


def _error_type(exc):
    return ERROR_TYPES.get(getattr(exc, 'status', None), 'unavailable')


def _failure(query, kb_name, error_type, answer='', **extra):
    return {'query': query, 'kb_name': kb_name, 'content': '', 'sources': [],
            'error_type': error_type, 'answer': answer, 'cache_hit': False, **extra}


def _identity(source):
    """原文身份+版本+范围；不同版本或范围不能被合并。"""
    location = source.get('location') or {}
    text = source.get('quote') or source.get('text') or ''
    return (source.get('document_id'), source.get('version'),
            location.get('block_start'), location.get('block_end'),
            hashlib.sha256(str(text).encode()).hexdigest()[:16])


def _authorized_sources(sources):
    """Drop passages whose material version this learner is not assigned."""
    from deeptutor.multi_user.context import get_current_user_or_none

    user = get_current_user_or_none()
    if user is None or user.is_admin:
        return sources
    from deeptutor.multi_user.learning_access import learning_material_allowed

    return [source for source in sources
            if learning_material_allowed(str(source.get('version') or '')[:16])]


def _turn_state(context):
    metadata = getattr(context, 'metadata', None) if context is not None else None
    if not isinstance(metadata, dict):
        return None, None, None
    return (metadata.setdefault('_heart_rag_cache', {}),
            metadata.setdefault('_heart_rag_tasks', {}),
            metadata.setdefault('_heart_projected_sources', {}))


def _mark(projected, sources):
    for position, source in enumerate(sources or [], 1):
        projected.setdefault(_identity(source), {
            'index': int(source.get('index') or position),
            'rag_source_id': source.get('rag_source_id'),
            'source_id': source.get('source_id'),
            'evidence_id': source.get('source_id')})


def source_content(sources, budget_chars=None):
    """按完整条目组装证据；放不下的条目只留可恢复的短 ID 和位置。"""
    lines = [f"教材检索结果（{len(sources)} 条）。引用时在句末写短 ID，例如 [S1]；"
             "服务端只对本轮已披露来源生成正式链接。"]
    used = 0
    for source in sources:
        identifier = source.get('short_id') or f"S{source['index']}"
        page = f"，第{source['page']}页" if source.get('page') else ""
        location = f"第{source['chapter_id']}章{page}，{source.get('location', {}).get('section', '')}"
        head = f"[{identifier}] {location} (source_id={source['rag_source_id']})"
        block = f"{head}\n{source['text']}"
        if budget_chars and used and used + len(block) > budget_chars:
            lines.append(f"{head}\n（原文未展开；需要时用 read_source 读取 {identifier}。）")
            continue
        lines.append(block)
        used += len(block)
    return '\n\n'.join(lines)


def _repeat(result, projected):
    """同一原文已在模型上下文中：只提示编号，不再堆叠全文。"""
    sources = result.get('sources') or []
    fresh = [source for source in sources if _identity(source) not in projected]
    copied = copy.deepcopy(sources)
    if not fresh:
        references = '；'.join(f"[{source.get('short_id') or source['index']}] (source_id={source['rag_source_id']})" for source in sources)
        return {**result, 'sources': copied,
                'content': f'本轮已返回相同教材原文（短 ID 不变）：{references}。需要全文时用 read_source 补读。'}
    return {**result, 'sources': copied, 'content': source_content(fresh)}


def _budgeted(result, budget_chars):
    """只收窄证据正文；短提示和已符合预算的内容保持原样。"""
    content = str(result.get('content') or '')
    if not budget_chars or not result.get('sources') or len(content) <= budget_chars:
        return result
    return {**result, 'content': source_content(result['sources'], budget_chars)}


def _native_user_payload(query, limit, mode, context):
    """Bind the authenticated native user, workspace and live session."""
    from uuid import uuid4
    from deeptutor.multi_user.context import get_current_user_or_none
    from deeptutor.services.workspace.context import current_workspace_id
    from knowledge.course_config import COURSE_ID

    user = get_current_user_or_none()
    session_id = str(getattr(context, 'session_id', '') or '') if context is not None else ''
    workspace_id = str(current_workspace_id() or '')
    if user is None or not session_id:
        logging.getLogger(__name__).warning(
            '课程检索缺少原生绑定 user=%s session=%s workspace=%s',
            user is not None, bool(session_id), bool(workspace_id))
        return None
    return {'student_id': user.id, 'username': user.username, 'course_id': COURSE_ID,
            'session_id': session_id, 'workspace_id': workspace_id,
            'request_id': uuid4().hex, 'query': query, 'mode': mode, 'limit': limit,
            'chapter_id': None, 'section_id': None}


async def search_course(query, limit=6, mode=DEFAULT_MODE, context=None, budget_chars=None):
    """Worker entry: search the host's resident LightRAG.

    Host-native turns use the task receipt; ordinary native login accounts use
    the user/workspace/session binding. Returns ``None`` only when neither is
    available, so a non-native surface can keep its own local index.
    """
    from .learning_tool_adapter import current_learning_context
    native_payload = None
    if current_learning_context() is None:
        native_payload = _native_user_payload(query, limit, mode, context)
        if native_payload is None:
            return None
    pipeline = CoursePipeline(PROVIDER, None)
    return await pipeline.search(query, canonical_kb_name(), mode=mode, limit=limit,
                                 _heart_context=context, _native_payload=native_payload,
                                 budget_chars=budget_chars)


class CoursePipeline:
    def __init__(self, provider, kb_base_dir):
        self.provider, self.kb_base_dir = provider, kb_base_dir

    async def search(self, query, kb_name, **kwargs):
        from deeptutor.services.rag.provider_binding import load_kb_config_entry
        from .client import BackendUnavailable
        from .learning_tool_adapter import current_learning_context
        if self.kb_base_dir is not None:
            entry = load_kb_config_entry(self.kb_base_dir, kb_name)
            if entry.get('rag_provider') != self.provider:
                raise ValueError('教材KB绑定不一致')
            status = await asyncio.to_thread(probe, self.provider, entry.get('external_path'))
            if not status.ready:
                return _failure(query, kb_name, 'not_ready', status.failure_summary)
        # kb_base_dir is None: the worker path. Readiness is the host endpoint's
        # call (fixed_book.active()); a second file-layout check here can only
        # produce false negatives.
        context = kwargs.get('_heart_context') or _context.get()
        native_payload = kwargs.get('_native_payload')
        learning = current_learning_context()
        if learning is None and native_payload is None:
            raise BackendUnavailable('课程教材查询缺少任务授权上下文')
        limit = max(1, min(int(kwargs.get('limit') or 6), 12))
        mode = str(kwargs.get('mode') or DEFAULT_MODE)
        budget_chars = kwargs.get('budget_chars')
        chapter_id, section_id = kwargs.get('chapter_id'), kwargs.get('section_id')
        # 缓存只挂在当前回合的context.metadata：不跨用户、任务或分支。
        cache, tasks, projected = _turn_state(context)
        if native_payload is not None:
            scope = ('native', native_payload['student_id'],
                     native_payload['session_id'], native_payload['workspace_id'])
        else:
            scope = tuple(sorted((learning.check.material_versions or {}).items()))
        key = (kb_name, query, mode, limit, chapter_id, section_id, scope)
        if cache is not None and key in cache:
            result = _repeat(cache[key], projected)
            _mark(projected, result.get('sources'))
            return _budgeted({**result, 'cache_hit': True}, budget_chars)
        task = tasks.get(key) if tasks is not None else None
        if task is None:
            task = asyncio.create_task(self._execute(
                query, kb_name, mode, limit, chapter_id, section_id, context,
                learning, native_payload))
            if tasks is not None:
                tasks[key] = task
        try:
            result = await task
        finally:
            if tasks is not None and task.done():
                tasks.pop(key, None)
        if cache is not None and result.get('error_type') not in ('not_ready', 'unavailable', 'timeout'):
            # 深拷贝：调用方（如图表附加）对sources的修改不能污染后续命中。
            cache[key] = {**result, 'sources': copy.deepcopy(result.get('sources') or [])}
        if projected is None or not result.get('sources'):
            return _budgeted({**result, 'cache_hit': False}, budget_chars)
        projection = _repeat(result, projected)
        _mark(projected, result['sources'])
        return _budgeted({**projection, 'cache_hit': False}, budget_chars)

    async def _execute(self, query, kb_name, mode, limit, chapter_id, section_id, context,
                       learning, native_payload=None):
        from .client import BackendUnavailable, DeepTutorBackend
        from .native_grounding import prepare_retrieval
        from knowledge.lightrag.retrieval import as_textbook_chunk
        payload = native_payload if native_payload is not None else {
            **learning.check.model_dump(), 'query': query, 'mode': mode, 'limit': limit,
            'chapter_id': chapter_id, 'section_id': section_id}
        started = time.perf_counter()
        try:
            backend = DeepTutorBackend(base_url=os.getenv('DEEPTUTOR_HOST_URL', 'http://127.0.0.1:8000'))
            initialized = time.perf_counter()
            if native_payload is not None:
                result = await backend.native_user_course_search(payload)
            else:
                result = await backend.native_course_search(payload)
        except BackendUnavailable as exc:
            return _failure(query, kb_name, _error_type(exc), str(exc))
        received = time.perf_counter()
        usage = result.get('usage') or {}
        stages = [*(usage.get('stages') or []),
                  {'stage': 'worker.client_init', 'seconds': initialized - started, 'includes_children': False},
                  {'stage': 'worker.host_roundtrip', 'seconds': received - initialized, 'includes_children': True}]
        result = {**result, 'usage': {**usage, 'stages': stages}}
        if result.get('status') == 'no_evidence' or not result.get('sources'):
            return _failure(query, kb_name, 'no_evidence', '教材原文没有匹配段落',
                            status=result.get('status'), trace=result.get('trace') or [],
                            usage=result.get('usage') or {})
        chunks = [as_textbook_chunk(row) for row in result.get('sources') or ()]
        verified = time.perf_counter()
        try:
            sources = await asyncio.to_thread(prepare_retrieval, query, chunks, context, kb_name)
        except (ValueError, OSError):
            return _failure(query, kb_name, 'no_evidence', '教材原文未通过核验',
                            status=result.get('status'), trace=result.get('trace') or [],
                            usage=result.get('usage') or {})
        prepared = time.perf_counter()
        stages.extend([
            {'stage': 'worker.chunk_projection', 'seconds': verified - received, 'includes_children': False},
            {'stage': 'worker.grounding', 'seconds': prepared - verified, 'includes_children': False},
            {'stage': 'worker.execute', 'seconds': prepared - started, 'includes_children': True},
        ])
        if not sources:
            return _failure(query, kb_name, 'no_evidence', '教材原文未通过核验',
                            status=result.get('status'), trace=result.get('trace') or [],
                            usage=result.get('usage') or {})
        unique, seen = [], set()
        for item in sources:
            identity = _identity(item)
            if identity in seen:
                continue
            seen.add(identity)
            unique.append(item)
        sources = _authorized_sources(unique)
        if not sources:
            return _failure(query, kb_name, 'permission', '教材原文超出当前账号的授权范围',
                            status=result.get('status'), trace=result.get('trace') or [],
                            usage=result.get('usage') or {})
        logging.getLogger(__name__).info('course_rag provider=%s engine=lightrag sources=%d',
                                         self.provider, len(sources))
        content = source_content(sources)
        return {'query': query, 'kb_name': kb_name, 'content': content, 'sources': sources,
                'host_engine': 'lightrag', 'backend': 'lightrag', 'mode': mode,
                'status': result.get('status'), 'trace': result.get('trace') or [],
                'usage': result.get('usage') or {},
                'source_binding': result.get('source_binding') or {}}

    async def initialize(self, **kwargs):
        raise ValueError('固定教材沿用现有索引，不支持从此入口重建')

    async def add_documents(self, **kwargs):
        return await self.initialize(**kwargs)

    async def delete(self, **kwargs):
        raise ValueError('固定教材索引只读，不能由KB操作删除')


def inventory(entry):
    """真实教材目录；不把候选索引内部文件当成教材文件。"""
    if Path(str(entry.get('external_path') or '')).resolve() != source_root():
        return None
    from knowledge.pdf_reader import documents
    return [f"chapters/chapter_{row['chapter_id']:02d}/chapter_{row['chapter_id']:02d}.generated.pdf"
            for row in documents()], True


def install():
    from deeptutor.services.rag import factory, index_probe
    from deeptutor.multi_user import knowledge_access
    from deeptutor.knowledge import manifest
    if getattr(factory._build_pipeline, '_heart_course_provider', False):
        return
    original_build, original_probe = factory._build_pipeline, index_probe.inspect_provider_index
    original_manifest = knowledge_access.build_manifest
    factory.KNOWN_PROVIDERS = frozenset((*factory.KNOWN_PROVIDERS, PROVIDER))

    def build(provider, kb_base_dir, **kwargs):
        return CoursePipeline(provider, kb_base_dir) if provider == PROVIDER \
            else original_build(provider, kb_base_dir, **kwargs)

    def inspect(provider, storage_dir):
        return probe(provider, storage_dir) if provider == PROVIDER else original_probe(provider, storage_dir)

    def build_manifest(**kwargs):
        entry = kwargs.get('entry') or {}
        if entry.get('rag_provider') == PROVIDER:
            kwargs['entry'] = {**entry, 'type': 'heart-course-inventory'}
        return original_manifest(**kwargs)

    manifest._REMOTE_INVENTORY_READERS['heart-course-inventory'] = inventory
    build._heart_course_provider = True
    factory._build_pipeline = build
    index_probe.inspect_provider_index = inspect
    knowledge_access.build_manifest = build_manifest


def register_course_sources(course_id):
    """挂载唯一规范KB并解除两个旧课程资源；重复迁移无额外变化。"""
    from deeptutor.knowledge.manager import KnowledgeBaseManager
    from deeptutor.services.path_service import get_path_service
    from deeptutor.services.courses import CourseResourceNotFoundError, CourseService
    install()
    manager = KnowledgeBaseManager(str(get_path_service().get_knowledge_bases_root()))
    name = canonical_kb_name()
    entry = manager.get_kb_entry(name)
    if entry is None:
        manager.register_linked_kb(name, str(source_root()), PROVIDER,
            description='课程教材只读检索 · LightRAG')
    elif (entry.get('rag_provider') != PROVIDER
          or Path(str(entry.get('external_path') or '')).resolve() != source_root()):
        raise ValueError('课程KB名称已被其他资源占用')
    courses = CourseService()
    courses.attach_resource(course_id, kind='knowledge_base', ref_id=name, label='课程教材 · LightRAG')
    for resource in courses.get(course_id).resources:
        if resource.kind == 'knowledge_base' and resource.ref_id in legacy_aliases():
            try:
                courses.detach_resource(course_id, resource.id)
            except CourseResourceNotFoundError:
                continue
    return [name]
