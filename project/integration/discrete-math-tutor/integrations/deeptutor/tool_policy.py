"""宿主教学工具范围：保留原版实现，在模型目录与调用边界隐藏无关集成。"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps

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
    """课程教材预检索只服务 chat 的课程问题。"""
    from .course_rag_provider import canonical_kb_name
    if canonical_kb_name() not in (getattr(context, 'knowledge_bases', None) or []):
        return False
    from .course_scope import is_course_question
    return (getattr(context, 'active_capability', None) not in (None, 'chat')
            or not is_course_question(getattr(context, 'user_message', '')))


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

    @wraps(original_augment)
    def augment(pipeline, name, args, context):
        kwargs = original_augment(pipeline, name, args, context)
        if active_scope() and name == 'rag':
            kwargs['_heart_context'] = context
            context.metadata.setdefault('_heart_citation_offset', _citation_offset.get())
        elif active_scope() and name == 'read_source':
            kwargs['source_index'] = context.metadata.get('source_index') or {}
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
        if active_scope() and not visible(name):
            raise KeyError('工具未在当前教学项目中启用')
        return await original_execute(registry, name, **kwargs)

    @wraps(original_compose)
    def compose(pipeline, context):
        context.metadata['heart_skip_kb_seed'] = skip_kb_seed(context)
        context.metadata.setdefault('_heart_citation_offset', _citation_offset.get())
        names = original_compose(pipeline, context)
        if active_scope():
            names = [name for name in names if visible(name)]
            # 宿主教材使用已有索引，不依赖原生 KB 记录；仍遵守阶段白名单和独占能力。
            if not pipeline._exclusive_capability_active(context):
                for name in ('rag', 'kb_files'):
                    if (context.allowed_builtin_tools is None or name in context.allowed_builtin_tools) and pipeline.tool_lookup.get(name) is not None:
                        names.append(name)
                names = list(dict.fromkeys(names))
            # 原生循环在回合开始时固定 schema，检索和补读必须同时挂载。
            if (('rag' in names or any(key.startswith('rag-') for key in context.metadata.get('source_index', {})))
                    and (context.allowed_builtin_tools is None or 'read_source' in context.allowed_builtin_tools)
                    and pipeline.tool_lookup.get('read_source') is not None):
                names = list(dict.fromkeys([*names, 'read_source']))
        return names

    get._heart_tool_policy = True
    ToolRegistry.get, ToolRegistry.list_tools = get, list_tools
    ToolRegistry.execute, ToolRegistry.deferred_tools = execute, deferred
    AgenticLoopPipeline._compose_enabled_tools = compose
    AgenticLoopPipeline._augment_tool_kwargs = augment
    extensions.all_loop_capabilities = all_extensions


@contextmanager
def teaching_tool_scope(citation_offset=0):
    install_tool_policy()
    token = _active.set(True)
    citation_token = _citation_offset.set(citation_offset)
    try:
        yield
    finally:
        _citation_offset.reset(citation_token)
        _active.reset(token)
