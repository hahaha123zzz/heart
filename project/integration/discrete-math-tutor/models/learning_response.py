"""第五层只读回答协议；状态、题目答案与工具权限不由模型填写。"""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

PublishedText = Annotated[str, StringConstraints(strip_whitespace=False)]

SemanticType = Literal['direct_answer', 'definition', 'explanation', 'procedure', 'comparison',
    'worked_example', 'analogy', 'misconception', 'counterexample', 'formula_explanation',
    'visual_explanation', 'hint', 'recap', 'next_step', 'check_question', 'feedback']


class ResponseModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, str_strip_whitespace=True)


class BlockSpec(ResponseModel):
    block_id: str = Field(min_length=1, max_length=64)
    semantic_type: SemanticType
    required: bool = True
    depends_on: list[str] = Field(default_factory=list, max_length=6)
    task_frame_ids: list[str] = Field(default_factory=list, max_length=4)
    target_ref: str | None = None


class ResponsePlan(ResponseModel):
    schema_version: Literal['response-plan/v1'] = 'response-plan/v1'
    plan_id: str
    target_id: str
    strategy: str
    blocks: list[BlockSpec] = Field(min_length=1, max_length=6)

    @model_validator(mode='after')
    def dependencies(self):
        seen = set()
        for block in self.blocks:
            if block.block_id in seen or len(set(block.depends_on)) != len(block.depends_on):
                raise ValueError('duplicate_block_identity')
            if not set(block.depends_on) <= seen:
                raise ValueError('dependency_must_precede_block')
            seen.add(block.block_id)
        if not any(block.required for block in self.blocks):
            raise ValueError('required_block_missing')
        return self


class ContentClaim(ResponseModel):
    text: str = Field(min_length=1, max_length=2000)
    source_ids: list[str] = Field(min_length=1, max_length=8)
    provenance: Literal['quotation', 'paraphrase', 'derived_explanation', 'generated_example', 'analogy']


class GeneratedBlock(ResponseModel):
    block_id: str = Field(min_length=1, max_length=64)
    claims: list[ContentClaim] = Field(min_length=1, max_length=8)


class GeneratedResponse(ResponseModel):
    blocks: list[GeneratedBlock] = Field(min_length=1, max_length=6)


class PublishedBlock(ResponseModel):
    block_id: str = Field(min_length=1, max_length=64)
    claims: list[ContentClaim] = Field(default_factory=list, max_length=8)
    semantic_type: SemanticType
    status: Literal['published'] = 'published'
    rendered_text: PublishedText
    content_origin: Literal['generated', 'host_snapshot'] = 'generated'
    authority_ref: str | None = None

    @model_validator(mode='after')
    def publication_origin(self):
        if self.content_origin == 'generated' and (not self.claims or self.authority_ref is not None):
            raise ValueError('generated_claims_required')
        if self.content_origin == 'host_snapshot' and (not self.authority_ref or self.claims):
            raise ValueError('host_snapshot_requires_authority_without_generated_claims')
        return self


class LearningResponse(ResponseModel):
    schema_version: Literal['learning-response/v1'] = 'learning-response/v1'
    response_id: str
    plan: ResponsePlan
    status: Literal['complete', 'partial', 'in_progress']
    blocks: list[PublishedBlock]
    omitted: list[str] = Field(default_factory=list)
    leading_text: str = ''
    reply: PublishedText
