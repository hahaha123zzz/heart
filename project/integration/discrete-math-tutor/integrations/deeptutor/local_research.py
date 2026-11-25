"""原生ResearchPipeline的本地资料权限边界，不接管研究编排。"""
from contextvars import ContextVar
from functools import wraps

_scope = ContextVar('heart_local_research_kbs', default=None)
LOCAL_TOOLS = frozenset(('ask_user', 'rag', 'kb_files', 'read_source', 'lookup_figures',
    'workspace_list', 'workspace_read', 'workspace_search', 'workspace_present'))
LOCAL_PROVIDERS = frozenset(('heart-course-lightrag', 'llamaindex', 'lightrag', 'graphrag'))


def tool_allowed(name):
    return _scope.get() is None or name in LOCAL_TOOLS


def check_kb(name, kb_base_dir=None):
    from pathlib import Path
    from deeptutor.multi_user.knowledge_access import resolve_kb_metadata, resolve_for_rag
    selected = _scope.get()
    if selected is None:
        return
    resource = resolve_for_rag(name)
    allowed = [resolve_for_rag(ref) for ref in selected]
    metadata = resolve_kb_metadata(name) if resource is not None else None
    identity = (str(resource.base_dir.resolve()), resource.name) if resource else None
    identities = {(str(item.base_dir.resolve()), item.name) for item in allowed if item}
    if (identity not in identities or not metadata
            or metadata.get('rag_provider', 'llamaindex') not in LOCAL_PROVIDERS
            or kb_base_dir is not None and Path(kb_base_dir).resolve() != resource.base_dir.resolve()):
        raise ValueError('深入研究只能读取本轮选择的本地课程或上传知识库')


def install(policy_active, citation_offset):
    from deeptutor.agents.research.pipeline import ResearchPipeline, _BlockLoopHost, _citation_anchor_id
    from deeptutor.services.rag.service import RAGService
    if getattr(ResearchPipeline.run, '_heart_local_research', False):
        return
    original_run = ResearchPipeline.run
    original_prepare = ResearchPipeline._prepare_research_providers
    original_augment = ResearchPipeline._augment_tool_kwargs
    original_search = RAGService.search
    original_record = _BlockLoopHost._summarise_and_record
    original_reference = ResearchPipeline._format_reference_entry

    @wraps(original_run)
    async def run(pipeline, *, context, **kwargs):
        if not policy_active.get() and not context.knowledge_bases:
            return await original_run(pipeline, context=context, **kwargs)
        from .course_rag_provider import canonical_names
        # 旧会话/显式选择中的课程别名归一；其他上传KB保持原顺序。
        context.knowledge_bases = canonical_names(context.knowledge_bases or [])
        token = _scope.set(frozenset(context.knowledge_bases))
        try:
            for name in context.knowledge_bases:
                check_kb(name)
            from .course_rag_provider import retrieval_context
            with retrieval_context(context):
                return await original_run(pipeline, context=context, **kwargs)
        finally:
            _scope.reset(token)

    @wraps(original_prepare)
    async def prepare(pipeline, context):
        if _scope.get() is None:
            return await original_prepare(pipeline, context)
        # 本地研究不建立远端MCP连接；队列、工具组合及报告仍执行上游。
        pipeline._scientific_mcp_names = []

    @wraps(original_augment)
    def augment(pipeline, name, args, context):
        kwargs = original_augment(pipeline, name, args, context)
        if _scope.get() is not None and name == 'rag':
            kwargs['_heart_context'] = context
            context.metadata.setdefault('_heart_citation_offset', citation_offset.get())
        return kwargs

    @wraps(original_search)
    async def search(service, query, kb_name, **kwargs):
        check_kb(kb_name, service.kb_base_dir)
        return await original_search(service, query=query, kb_name=kb_name, **kwargs)

    @wraps(original_record)
    async def record(host, tool_calls, outcome):
        before = set(host._citations.get_all_citations())
        await original_record(host, tool_calls, outcome)
        if _scope.get() is None:
            return
        sources = [item for item in outcome.sources if item.get('type') == 'heart_textbook_evidence']
        groups = getattr(host._pipeline, '_heart_research_groups', {})
        events = list(sources)
        for citation_id in set(host._citations.get_all_citations()) - before:
            citation = host._citations.get_citation(citation_id) or {}
            if citation.get('tool_type') != 'rag':
                continue
            chunks = {str(item.get('chunk_id')) for item in citation.get('sources', [])}
            matched = [item for item in sources if str(item.get('chunk_id')) in chunks]
            if matched:
                anchor = _citation_anchor_id(citation_id)
                groups[citation_id] = matched
                events.append({'type':'heart_research_citation', 'anchor':anchor,
                    'source_ids':[item['source_id'] for item in matched]})
        host._pipeline._heart_research_groups = groups
        if events:
            await host._stream.sources(events, source='deep_research', stage='researching')

    @wraps(original_reference)
    def reference(pipeline, citations, citation_id):
        text = original_reference(pipeline, citations, citation_id)
        if text and _scope.get() is not None:
            rows = getattr(pipeline, '_heart_research_groups', {}).get(citation_id, [])
            text += ' ' + ' '.join(f'<a href="#heart-source-{item["index"]}">教材原文 {i}</a>'
                for i,item in enumerate(rows, 1))
        return text

    run._heart_local_research = True
    ResearchPipeline.run = run
    ResearchPipeline._prepare_research_providers = prepare
    ResearchPipeline._augment_tool_kwargs = augment
    RAGService.search = search
    _BlockLoopHost._summarise_and_record = record
    ResearchPipeline._format_reference_entry = reference
