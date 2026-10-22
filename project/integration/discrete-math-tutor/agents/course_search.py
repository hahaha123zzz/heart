"""Q3/Q5 共用检索边界；不改变路径解析，不实现检索引擎。"""
from dataclasses import replace
import json
import logging
import os
import re
import time

from agents.q3_navigation import SourceRef, source_from_chunk

log = logging.getLogger(__name__)


def explicit_chapters(message):
    from knowledge.course_navigation import _number
    return {number for value in re.findall(r'第([一二三四五六七八九十零\d]+)章', message)
            if (number := _number(value)) is not None}


class CourseSearch:
    def __init__(self, base, *, message, llm, backend=None, cancellation=None):
        self.base, self.message, self.llm = base, message, llm
        self.backend = backend
        self.cancellation = cancellation
        self.calls = []
        self.last_result = None
        self.coverage = None
        self._covered_sources = None

    def resolve(self, **kwargs):
        return self.base.resolve(**kwargs)

    def search(self, *, target, query, limit, preferred_types=()):
        chapters = explicit_chapters(self.message)
        side_question = bool(chapters and (len(chapters) > 1 or target.chapter_id not in chapters))
        search_target = replace(target, target_id='question', name=self.message,
                                chapter_id=next(iter(chapters)) if len(chapters) == 1 else None,
                                section_id=None, source_scope={}, version='') if side_question else target
        record = {'requested_backend': os.getenv('Q3_RETRIEVAL_MODE', 'existing'),
                  'actual_backend': 'not_started', 'target_id': target.target_id,
                  'side_question': side_question, 'fallback': False}
        self.calls.append(record)
        self.last_result = None
        started = time.monotonic()
        try:
            if self.cancellation:
                self.cancellation.check()
            exact = []
            exact_id, exact_version = target.target_id, target.version
            pointers = target.source_scope.get('source_refs', [])
            if len(pointers) == 1 and pointers[0].get('source_kind') == 'q2_navigation':
                exact_id = pointers[0].get('unit_id', '')
                exact_version = pointers[0].get('version', '')
            multiple = bool(self.coverage and self.coverage.requirements)
            if not side_question and not multiple and re.fullmatch(r'ch\d+:s\d+:b\d+', exact_id):
                from knowledge.course_navigation import read_target
                exact = read_target({'id': exact_id, 'version': exact_version})
                if not exact:
                    raise ValueError('精确教材目标已失效，不改为语义近似检索')
            if exact:
                record['actual_backend'] = 'q2_exact'
                record['document_identity'] = exact_version
                record['exact_target_id'] = exact_id
                sources = [source_from_chunk(chunk, index) for index, chunk in enumerate(exact[:limit])]
            elif self.backend is not None:
                record['actual_backend'] = 'lightrag' if hasattr(self.backend, 'backend') else 'injected'
                if self._covered_sources is not None:
                    sources = self._covered_sources
                    record['cached_coverage'] = True
                else:
                    selected = self.coverage or self.backend
                    sources = selected.search(target=search_target, query=query, limit=limit,
                                              preferred_types=preferred_types)
                    if self.coverage and self.coverage.requirements:
                        self._covered_sources = sources
                self.last_result = getattr(self.backend, 'last_result', None)
                if self.last_result:
                    record['model_binding'] = self.last_result.get('model_binding')
                    record['input_signature'] = self.last_result.get('input_signature')
                    record['index_identity'] = str(getattr(getattr(self.backend, 'backend', None), 'candidate', ''))
            else:
                mode = os.getenv('Q3_RETRIEVAL_MODE', 'stub').lower()
                record['actual_backend'] = 'local_llamaindex' if (mode in ('local', 'q2', 'local_llamaindex')
                    or type(self.base).__name__ == 'Q5Navigator') else 'existing'
                sources = self.base.search(target=search_target, query=query, limit=limit,
                                           preferred_types=preferred_types)
                if sources:
                    record['actual_backend'] = sources[0].location.get('retrieval_backend', record['actual_backend'])
                if record['actual_backend'] == 'local_llamaindex':
                    from knowledge.hybrid_retrieval import INDEX
                    from knowledge.local_rag.course_retrieval import index_signature
                    record['index_identity'] = {'path': str(INDEX), 'sha256': index_signature(INDEX)}
            record['retrieved_source_ids'] = [s.source_id for s in sources]
            # 先选择真实原文再分配本轮编号；发布时复用同一 evidence，而非重新检索。
            if sources and all(s.location.get('source') for s in sources) and (exact or not self.coverage):
                sources = self.select(self.message, sources)
            record.update(status='success' if sources else 'no_evidence',
                          selected_source_ids=[s.source_id for s in sources])
            return sources
        except BaseException as exc:
            record.update(status='failed', error_type=type(exc).__name__)
            raise
        finally:
            record['seconds'] = time.monotonic() - started
            log.info('course_search %s', json.dumps(record, ensure_ascii=False))

    def select(self, question, sources, *, subproblem='single'):
        from knowledge.grounded_citations import choose_evidence, settings
        from knowledge.lightrag.retrieval import as_textbook_chunk
        index = settings()
        if index is None:
            raise ValueError('新检索发布要求启用原文核验')
        bundle = choose_evidence(self.llm, question,
                                 [as_textbook_chunk(s.to_dict()) for s in sources], index)
        if self.coverage:
            from knowledge.lightrag.trace import stage
            stage(self.coverage.trace, 'q2_selection', sources,
                  [sources[e['retrieval_source_index']] for e in bundle.evidence],
                  'not_selected_by_q2; reason_not_returned', query=question, subproblem=subproblem)
        output = []
        for chunk, evidence in zip(bundle.sources, bundle.evidence):
            original = sources[evidence['retrieval_source_index']]
            output.append(replace(original, source_id=evidence['evidence_id'],
                document_id=evidence['document_id'], version=evidence['document_version'],
                chapter_id=chunk.chapter_id, section_id=chunk.section_id,
                text=chunk.text, quote=evidence['quote'],
                location={**original.location, 'source_spans':list(chunk.source_spans),
                    'block_start':evidence['source_block_id'], 'block_end':evidence['source_block_id'],
                    'block_char_start':evidence['block_start'], 'block_char_end':evidence['block_end'],
                    'retrieval_source_id':original.source_id, 'evidence':evidence}))
        return output

    @property
    def trace(self):
        return self.coverage.trace if self.coverage else []

    @property
    def coverage_report(self):
        return self.coverage.report if self.coverage else {}

    def tool_context(self, sources):
        if self.coverage:
            return self.coverage.tool_context(sources)
        from knowledge.lightrag.relationships import relationship_context
        return relationship_context((self.last_result or {}).get('graph_context', []), sources)


def shared_search(base, *, message, llm, navigator=None, cancellation=None):
    backend = navigator if navigator is not None else None
    if backend is None and os.getenv('Q3_RETRIEVAL_MODE', '').lower() == 'lightrag':
        from knowledge.course_config import COURSE_ID
        from knowledge.lightrag.retrieval import LightRagBackend
        from knowledge.lightrag.q3_adapter import LightRagNavigator
        path = os.environ.get('LIGHTRAG_CANDIDATE_PATH')
        if not path:
            raise ValueError('LightRAG 未提供索引路径，不能静默回退')
        backend = LightRagNavigator(base, LightRagBackend(path, authorized_course_ids={COURSE_ID},
            allow_candidate=os.getenv('LIGHTRAG_ALLOW_CANDIDATE') == '1'), cancellation=cancellation)
    search = CourseSearch(base, message=message, llm=llm, backend=backend, cancellation=cancellation)
    from knowledge.lightrag.q3_adapter import LightRagNavigator
    if isinstance(backend, LightRagNavigator):
        from knowledge.lightrag.coverage import CoverageNavigator, semantic_selection
        search.coverage = CoverageNavigator(backend, question=message,
            select=lambda requirement, refs: search.select(requirement.query, refs, subproblem=requirement.id),
            judge=lambda requirement, refs: semantic_selection(llm, requirement, refs), cancellation=cancellation)
    return search


def association_context(navigator, sources):
    """仅传入能链接本次原文的关联候选，不让图谱摘要变成独立证据。"""
    result = getattr(navigator, 'last_result', None) or {}
    links = {}
    for source in sources:
        original = source.location.get('evidence', {}).get('retrieval_source_id', source.source_id)
        links[original] = {'source_id': source.source_id, 'document_id': source.document_id,
                           'version': source.version, 'quote': source.quote,
                           'block_start': source.location.get('block_start')}
    output = []
    for row in result.get('graph_context', []):
        matched = [links[sid] for sid in row.get('original_source_ids', []) if sid in links]
        if not matched:
            continue
        item = {**row, 'original_sources': matched, 'evidence_eligible': False}
        if len(json.dumps(output + [item], ensure_ascii=False)) > 6000:
            break
        output.append(item)
        if len(output) == 8:
            break
    return output
