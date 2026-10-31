"""第四层内部需求执行器；候选必须由调用方核验证据支持，不能仅凭检索分数完成。"""
from agents.q3_navigation import SourceRef
from models.evidence_execution import EvidencePackage, RequirementCoverage, ToolExecutionReceipt


SCOPE = 'readonly_textbook_evidence; no_memory_write; no_navigation; no_publication'


def execute_requirements(request, *, retrieve, verify_support, check_cancelled=lambda: None):
    """每项最多一次取证；补召回由retrieve内部有界实现，语义核验不可省略。"""
    sources, coverage, receipts = {}, [], []
    for need in request.requirements:
        check_cancelled()
        accepted = []
        try:
            candidates = retrieve(need)
            for source in candidates:
                check_cancelled()
                if not isinstance(source, SourceRef):
                    raise ValueError('source_ref_required')
                target = need.target
                if (request.documents.get(source.document_id) != source.version or not source.text.strip()
                        or source.location.get('stub')
                        or (target and target.chapter_id is not None and source.chapter_id != target.chapter_id)
                        or (target and target.section_id is not None and source.section_id != target.section_id)):
                    continue
                if need.pixels_required and not any(i.get('model_saw_pixels') is True
                        and i.get('document_id') == source.document_id and i.get('version') == source.version
                        for i in source.image_refs):
                    continue
                if not verify_support(need, source):
                    continue
                if source.source_id in sources and sources[source.source_id] != source:
                    raise ValueError('source_identity_conflict')
                if source.source_id not in sources and len(sources) >= 24:
                    continue
                sources[source.source_id] = source
                if source.source_id not in accepted:
                    accepted.append(source.source_id)
            status, reason = ('satisfied', '') if accepted else ('missing', '未取得通过本项支持核验的证据')
            receipts.append(ToolExecutionReceipt(tool_call_id=need.id, tool_name='readonly_evidence', status='completed'))
        except (OSError, ValueError) as exc:
            accepted = []
            status, reason = 'unavailable', f'{type(exc).__name__}: {exc}'[:1000]
            receipts.append(ToolExecutionReceipt(tool_call_id=need.id, tool_name='readonly_evidence', status='failed', reason=reason))
        coverage.append(RequirementCoverage(requirement_id=need.id, status=status, source_ids=accepted, reason=reason))
    check_cancelled()
    missing = any(r.required and c.status != 'satisfied' for r, c in zip(request.requirements, coverage))
    state = ('partial' if any(c.status == 'satisfied' for c in coverage) else 'insufficient') if missing else 'completed'
    return EvidencePackage(request=request, status=state, sources=list(sources.values()), coverage=coverage, tool_receipts=receipts)
