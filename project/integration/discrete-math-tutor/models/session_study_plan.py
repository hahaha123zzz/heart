"""本次安排契约；时间与活动状态不是掌握度、成绩或长期偏好。"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StudyRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    goal: str = Field(min_length=1, max_length=500)
    scope: list[str] = Field(default_factory=list, max_length=12)
    time_budget_minutes: int | None = Field(default=None, ge=1, le=480)
    prior_knowledge: str = Field(default='', max_length=500)
    target_level: str = Field(default='', max_length=500)
    teaching_preference: str = Field(default='', max_length=500)
    practice_preference: Literal['none', 'optional', 'application'] = 'optional'
    value_sources: dict[str, Literal['explicit', 'confirmed_profile', 'confirmed_path', 'assumption']] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list, max_length=8)


class StudyItem(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    item_id: str = Field(min_length=1, max_length=64)
    objective_id: str | None = Field(default=None, max_length=64)
    kind: Literal['explain', 'example', 'compare', 'optional_check', 'review']
    title: str = Field(min_length=1, max_length=200)
    source_refs: list[dict] = Field(min_length=1, max_length=4)
    estimated_minutes: int = Field(ge=1, le=480)
    order_reason: str = Field(min_length=1, max_length=400)
    completion_criterion: str = Field(min_length=1, max_length=400)
    status: Literal['planned', 'in_progress', 'explained', 'skipped', 'done'] = 'planned'


class SessionStudyPlan(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    schema_version: Literal[1] = 1
    plan_id: str = Field(min_length=1, max_length=64)
    revision: int = Field(ge=1)
    student_id: str
    session_id: str
    course_id: str
    path_id: str | None = None
    path_revision: int | None = None
    base_plan_id: str | None = None
    base_revision: int = Field(default=0, ge=0)
    status: Literal['draft', 'active', 'paused', 'done'] = 'draft'
    request: StudyRequest
    items: list[StudyItem] = Field(min_length=1, max_length=16)
    current_item_id: str | None = None
    omitted: list[str] = Field(default_factory=list, max_length=16)

    @model_validator(mode='after')
    def budgets_and_identity(self):
        ids = [item.item_id for item in self.items]
        if len(ids) != len(set(ids)) or (self.current_item_id and self.current_item_id not in ids):
            raise ValueError('本次活动身份重复或当前位置无效')
        if self.request.time_budget_minutes is not None and sum(i.estimated_minutes for i in self.items) > self.request.time_budget_minutes:
            raise ValueError('安排预计总时间超过本次预算，请减少范围或活动')
        if self.request.practice_preference == 'none' and any(i.kind == 'optional_check' for i in self.items):
            raise ValueError('本次只讲不考，不得安排自测')
        return self
