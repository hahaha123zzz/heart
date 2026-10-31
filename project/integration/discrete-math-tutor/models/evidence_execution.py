"""第三/四层内部契约；形状校验不替代原文核验、语义支持或业务授权。"""
from typing import Literal

from pydantic import Field, computed_field, model_validator

from agents.q3_navigation import LearningTarget, SourceRef
from models.input_understanding import ContextHeader, Constraint, StrictModel


class EvidenceRequirement(StrictModel):
    id: str = Field(min_length=1, max_length=64)
    query: str = Field(min_length=1, max_length=4000)
    kind: Literal['text', 'image', 'table', 'formula'] = 'text'
    required: bool = True
    target: LearningTarget | None = None
    pixels_required: bool = False

    @model_validator(mode='after')
    def pixel_scope(self):
        if self.pixels_required and self.kind != 'image':
            raise ValueError('pixels_require_image')
        return self


class EvidenceRequest(StrictModel):
    schema_version: Literal['evidence-execution-v1'] = 'evidence-execution-v1'
    request_id: str = Field(min_length=1, max_length=64)
    decision_id: str = Field(min_length=1, max_length=128)
    context: ContextHeader
    documents: dict[str, str] = Field(min_length=1, max_length=32)
    requirements: list[EvidenceRequirement] = Field(min_length=1, max_length=12)
    constraints: list[Constraint] = Field(default_factory=list, max_length=4)

    @model_validator(mode='after')
    def bound_request(self):
        if not self.context.task_id or self.context.task_revision is None:
            raise ValueError('claimed_task_required')
        if len({r.id for r in self.requirements}) != len(self.requirements):
            raise ValueError('duplicate_requirement')
        if any(not key.strip() or not version.strip() for key, version in self.documents.items()):
            raise ValueError('document_version_required')
        return self


class RequirementCoverage(StrictModel):
    requirement_id: str = Field(min_length=1, max_length=64)
    status: Literal['satisfied', 'missing', 'unavailable']
    source_ids: list[str] = Field(default_factory=list, max_length=24)
    reason: str = Field(default='', max_length=1000)

    @model_validator(mode='after')
    def explicit_outcome(self):
        if self.status == 'satisfied' and not self.source_ids:
            raise ValueError('support_source_required')
        if self.status != 'satisfied' and not self.reason.strip():
            raise ValueError('missing_reason_required')
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError('duplicate_support_source')
        return self


class ToolExecutionReceipt(StrictModel):
    tool_call_id: str = Field(min_length=1, max_length=128)
    tool_name: str = Field(min_length=1, max_length=128)
    status: Literal['completed', 'requested', 'failed', 'cancelled']
    reason: str = Field(default='', max_length=1000)


class EvidencePackage(StrictModel):
    request: EvidenceRequest
    status: Literal['completed', 'partial', 'insufficient', 'failed', 'cancelled']
    sources: list[SourceRef] = Field(default_factory=list, max_length=24)
    coverage: list[RequirementCoverage] = Field(max_length=12)
    tool_receipts: list[ToolExecutionReceipt] = Field(default_factory=list, max_length=24)

    @model_validator(mode='after')
    def consistent_package(self):
        requirements = {r.id: r for r in self.request.requirements}
        coverage = {item.requirement_id: item for item in self.coverage}
        if len(coverage) != len(self.coverage) or coverage.keys() != requirements.keys():
            raise ValueError('coverage_must_match_requirements')
        sources = {source.source_id: source for source in self.sources}
        if len(sources) != len(self.sources) or any(not key.strip() for key in sources):
            raise ValueError('source_identity_conflict')
        for source in sources.values():
            if self.request.documents.get(source.document_id) != source.version:
                raise ValueError('source_outside_document_scope')
            if not source.text.strip() or source.location.get('stub'):
                raise ValueError('source_not_real_material')
        for item in self.coverage:
            if not set(item.source_ids) <= sources.keys():
                raise ValueError('coverage_unknown_source')
            target = requirements[item.requirement_id].target
            if target and any((target.chapter_id is not None and sources[key].chapter_id != target.chapter_id)
                              or (target.section_id is not None and sources[key].section_id != target.section_id)
                              for key in item.source_ids):
                raise ValueError('support_outside_target_scope')
            if requirements[item.requirement_id].pixels_required and item.status == 'satisfied':
                if not any(image.get('model_saw_pixels') is True
                           and image.get('document_id') == sources[key].document_id
                           and image.get('version') == sources[key].version
                           for key in item.source_ids for image in sources[key].image_refs):
                    raise ValueError('pixel_evidence_required')
        if self.status == 'completed' and self.missing_required:
            raise ValueError('required_evidence_incomplete')
        if self.status == 'insufficient' and not self.missing_required:
            raise ValueError('insufficient_without_missing_requirement')
        if len({r.tool_call_id for r in self.tool_receipts}) != len(self.tool_receipts):
            raise ValueError('duplicate_tool_receipt')
        return self

    @computed_field
    @property
    def missing_required(self) -> list[str]:
        required = {r.id for r in self.request.requirements if r.required}
        return [c.requirement_id for c in self.coverage
                if c.requirement_id in required and c.status != 'satisfied']

    @computed_field
    @property
    def ready_for_composition(self) -> bool:
        return self.status == 'completed' and not self.missing_required

    def checkpoint_payload(self):
        return self.model_dump(exclude={'missing_required', 'ready_for_composition'}, mode='json')
