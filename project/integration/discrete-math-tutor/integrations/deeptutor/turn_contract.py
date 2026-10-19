"""宿主与独立后端共享的回合契约；不包含问题、回答或教材引文。"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .session_bridge import SessionBindingRequest


class SourceRect(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    page: int = Field(ge=1)
    x1: float = Field(ge=0, lt=1)
    y1: float = Field(ge=0, lt=1)
    x2: float = Field(gt=0, le=1)
    y2: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def ordered(self):
        if self.x1 >= self.x2 or self.y1 >= self.y2:
            raise ValueError("教材坐标范围无效")
        return self


class SourcePointer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["selection", "section", "citation"]
    document_id: str = Field(min_length=1, max_length=100)
    version: str = Field(pattern=r"^[a-f0-9]{64}$")
    chapter_id: int = Field(ge=1)
    section_id: int | None = Field(default=None, ge=1)
    evidence_id: str | None = Field(default=None, max_length=128)
    rects: list[SourceRect] = Field(default_factory=list, max_length=80)


class TurnProjection(SessionBindingRequest):
    task_id: str = Field(min_length=1, max_length=64)
    task_revision: int = Field(ge=1)
    outcome: Literal["completed", "awaiting_clarification", "failed", "cancelled"]
    result_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    sources: list[SourcePointer] = Field(default_factory=list, max_length=32)


class TurnCursor(SessionBindingRequest):
    task_id: str = Field(min_length=1, max_length=64)
    task_revision: int = Field(ge=1)
    after_seq: int = Field(default=0, ge=0)
