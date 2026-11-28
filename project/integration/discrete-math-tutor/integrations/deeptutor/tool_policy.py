"""宿主教学工具范围：保留原版实现，在模型目录与调用边界隐藏无关集成。"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import re

from . import tool_disclosure as disclosure

# 当前产品不使用这些外部集成；需要恢复时只修改此处，不删除固定上游源码。
HIDDEN_TOOLS = frozenset((
    'obsidian_search','obsidian_read','obsidian_list','obsidian_backlinks','obsidian_links','obsidian_tags',
    'obsidian_create_note','obsidian_append','obsidian_set_property',
    'propose_partner','invoke_other','partner_read','partner_memorize','partner_search',
    'inspect_setup','apply_setting','request_credential','run_setup_job','cron',
))
HIDDEN_EXTENSIONS = frozenset(('obsidian','marginnote4','ima','setup','partner_authoring','partner_group'))
HIDDEN_MODULES = ('deeptutor.capabilities.marginnote4.', 'deeptutor.capabilities.ima.')
_active = ContextVar('heart_teaching_tool_policy', default=False)
_citation_offset = ContextVar('heart_citation_offset', default=0)


def learning_course_scope():
    """原生学生回合也使用已授权固定教材；不依赖旧宿主转发上下文。"""
    from deeptutor.multi_user.context import get_current_user_or_none
    from deeptutor.multi_user.learning_access import current_learning_policy
    user=get_current_user_or_none()
    if user is None or user.is_admin:
        return False
    policy=current_learning_policy()
    return bool(policy and 'reading' in policy.get('allowed_surfaces',['chat','reading'])
                and (policy.get('reading') or {}).get('material_ids'))


def active_scope():
    return _active.get() or learning_course_scope()


def hidden_names():
    from deeptutor.tools.builtin_specs import BUILTIN_TOOL_SPECS
    return HIDDEN_TOOLS | {spec.name for spec in BUILTIN_TOOL_SPECS
                           if spec.class_path.startswith(HIDDEN_MODULES)}


def visible(name):
    from deeptutor.tools.builtin_specs import TOOL_ALIASES
    canonical = TOOL_ALIASES.get(name, (name, {}))[0]
    return canonical not in hidden_names()


def skip_kb_seed(context):
    """课程教材预检索只服务 chat 的课程问题；纯目录题不预取正文。"""
    from .course_rag_provider import canonical_kb_name
    if canonical_kb_name() not in (getattr(context, 'knowledge_bases', None) or []):
        return False
    from .course_scope import is_course_question
    if (getattr(context, 'active_capability', None) not in (None, 'chat')
            or not is_course_question(getattr(context, 'user_message', ''))):
        return True
    return not (textbook_tools(context) - {'kb_files'})


CATALOG_INTENT = re.compile(r"目录|章节|章名|有哪些章|哪几章|共.{0,3}章|全书(?:结构|目录|章节)")
# 单个“哪”不再算讲解：目录问句里的“哪些/哪几章”必须保持纯目录。
EXPLAIN_INTENT = re.compile(r"解释|讲解|定义|概念|为什么|怎么|如何|比较|区别|原理|推导|什么|在哪|哪一章|哪一节|哪一页|哪几页|是什么|多少|是否|吗|讲|涉及")


def textbook_tools(context):
    """本回合应挂载的教材工具；短问和问候不挂教材工具。

    目录题只给目录，概念题给检索和补读；两者都有时按混合意图补齐。
    阅读视图和其他能力沿用原来的完整教材工具面。
    """
    from .course_scope import is_course_question
    metadata = getattr(context, 'metadata', None) or {}
    if metadata.get('reading_viewport'):
        return {'rag', 'kb_files', 'read_source'}
    if getattr(context, 'active_capability', None) not in (None, 'chat'):
        return {'rag', 'kb_files', 'read_source'}
    message = str(getattr(context, 'user_message', '') or '')
    wanted = set()
    catalog = bool(CATALOG_INTENT.search(message))
    if catalog:
        wanted.add('kb_files')
    # 纯目录问题不携带正文；同时要求解释时才补检索。
    if is_course_question(message) and not (catalog and not EXPLAIN_INTENT.search(message)):
        wanted.update(('rag', 'read_source'))
    return wanted


def install_tool_policy():
    from deeptutor.runtime.registry.tool_registry import ToolRegistry
    from deeptutor.agents.loop.pipeline import AgenticLoopPipeline
    from deeptutor.capabilities import registry as extensions
    if getattr(ToolRegistry.get, '_heart_tool_policy', False):
        return
    original_get, original_list = ToolRegistry.get, ToolRegistry.list_tools
    original_execute, original_deferred = ToolRegistry.execute, ToolRegistry.deferred_tools
    original_compose = AgenticLoopPipeline._compose_enabled_tools
    original_augment = AgenticLoopPipeline._augment_tool_kwargs
    original_schemas = AgenticLoopPipeline._build_llm_tool_schemas
    original_manifest = AgenticLoopPipeline._tool_manifest

    @wraps(original_augment)
    def augment(pipeline, name, args, context):
        kwargs = original_augment(pipeline, name, args, context)
        if active_scope() and name == 'rag':
            kwargs['_heart_context'] = context
            context.metadata.setdefault('_heart_citation_offset', _citation_offset.get())
        elif active_scope() and name == 'read_source':
            index = dict(context.metadata.get('source_index') or {})
            index.update(context.metadata.get('_heart_short_index') or {})
            kwargs['source_index'] = index
        elif active_scope() and name == 'load_tools':
            loader = disclosure.current_loader()
            if loader is not None:
                kwargs['_tool_loader'] = loader
        return kwargs
    original_extensions = extensions.all_loop_capabilities

    @wraps(original_extensions)
    def all_extensions():
        values = original_extensions()
        return tuple(value for value in values if value.name not in HIDDEN_EXTENSIONS) if active_scope() else values

    @wraps(original_get)
    def get(registry, name):
        if active_scope() and not visible(name):
            return None
        return original_get(registry, name)

    @wraps(original_list)
    def list_tools(registry):
        names = original_list(registry)
        return [name for name in names if visible(name)] if active_scope() else names

    @wraps(original_deferred)
    def deferred(registry):
        tools = original_deferred(registry)
        return [tool for tool in tools if visible(tool.name)] if active_scope() else tools

    @wraps(original_execute)
    async def execute(registry, name, /, **kwargs):
        if not active_scope():
            return await original_execute(registry, name, **kwargs)
        if not visible(name):
            raise KeyError('工具未在当前教学项目中启用')
        try:
            disclosure.require_loaded(disclosure.current_loader(), name)
        except KeyError:
            from deeptutor.core.tool_protocol import ToolResult
            return ToolResult(content='该工具需要先调用 load_tools 加载。', success=False)
        return await original_execute(registry, name, **kwargs)

    @wraps(original_compose)
    def compose(pipeline, context):
        context.metadata['heart_skip_kb_seed'] = skip_kb_seed(context)
        context.metadata.setdefault('_heart_citation_offset', _citation_offset.get())
        names = original_compose(pipeline, context)
        direct = ()
        if active_scope():
            names = [name for name in names if visible(name)]
            # 宿主教材使用已有索引，不依赖原生 KB 记录；仍遵守阶段白名单和独占能力。
            if not pipeline._exclusive_capability_active(context):
                scene = textbook_tools(context)
                for name in ('rag', 'kb_files'):
                    if name not in scene:
                        # 目录题不携带正文，短问也不挂教材工具。
                        names = [item for item in names if item != name]
                    elif (context.allowed_builtin_tools is None or name in context.allowed_builtin_tools) and pipeline.tool_lookup.get(name) is not None:
                        names.append(name)
                names = list(dict.fromkeys(names))
                # 目录题只有 kb_files 时直接可调用，避免为此多一轮发现往返。
                if scene == {'kb_files'}:
                    direct = ('kb_files',)
            has_source_index = bool(context.metadata.get('_heart_short_index')) or any(
                key.startswith('rag-') for key in context.metadata.get('source_index', {}))
            # 原生循环在回合开始时固定 schema，检索和补读必须同时挂载。
            if (('rag' in names or has_source_index)
                    and (context.allowed_builtin_tools is None or 'read_source' in context.allowed_builtin_tools)
                    and pipeline.tool_lookup.get('read_source') is not None):
                names = list(dict.fromkeys([*names, 'read_source']))
            elif not has_source_index:
                names = [name for name in names if name != 'read_source']
            disclosure.prepare(pipeline, context, names, direct=direct)
        else:
            disclosure.reset()
        return names

    @wraps(original_schemas)
    def schemas(pipeline, enabled_tools, context):
        if not active_scope():
            return original_schemas(pipeline, enabled_tools, context)
        return disclosure.filter_schemas(
            disclosure.current_loader(), original_schemas(pipeline, enabled_tools, context))

    @wraps(original_manifest)
    def manifest(pipeline, enabled_tools):
        loader = disclosure.current_loader() if active_scope() else None
        if loader is None:
            return original_manifest(pipeline, enabled_tools)
        visible_names = [name for name in enabled_tools if name not in loader.deferred]
        text = original_manifest(pipeline, visible_names)
        pending = sorted(loader.deferred - loader.loaded)
        if pending:
            try:
                lines = pipeline.tool_lookup.build_prompt_text(
                    pending, format="list", language=getattr(pipeline, 'language', 'zh'))
            except Exception:
                lines = "\n".join(f"- `{name}`" for name in pending)
            text += "\n按需工具（这里只列名称和用途；调用前先用 load_tools 加载）：\n" + lines
        return text

    get._heart_tool_policy = True
    ToolRegistry.get, ToolRegistry.list_tools = get, list_tools
    ToolRegistry.execute, ToolRegistry.deferred_tools = execute, deferred
    AgenticLoopPipeline._compose_enabled_tools = compose
    AgenticLoopPipeline._augment_tool_kwargs = augment
    AgenticLoopPipeline._build_llm_tool_schemas = schemas
    AgenticLoopPipeline._tool_manifest = manifest
    extensions.all_loop_capabilities = all_extensions


@contextmanager
def teaching_tool_scope(citation_offset=0):
    install_tool_policy()
    token = _active.set(True)
    citation_token = _citation_offset.set(citation_offset)
    try:
        yield
    finally:
        disclosure.reset()
        _citation_offset.reset(citation_token)
        _active.reset(token)
