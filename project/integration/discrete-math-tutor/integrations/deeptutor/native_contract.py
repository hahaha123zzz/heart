"""宿主与完整原生运行时的类型化边界；执行权限仍由原生资源与授权层核验。"""
import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator
from models.interaction_preferences import InteractionPreferences

Identifier = Annotated[str, Field(min_length=1, max_length=100)]
# 新字段缺省时沿用升级前的宿主收据，显式非默认值仍参与幂等校验。
ADDITIONAL_TURN_FIELDS = (
    'question_notebook_references', 'mastery_answer', 'mastery_skip', 'parent_message_id',
    'followup_question_context', 'selection_tutor_context', 'capability_once', 'auto_route',
)


class NativeTurnOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    capability: str = Field(default="chat", min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_-]*$")
    tools: list[Identifier] | None = Field(default=None, max_length=100)
    config: dict[str, Any] = Field(default_factory=dict)
    knowledge_bases: list[Identifier] = Field(default_factory=list, max_length=32)
    skills: list[Identifier] = Field(default_factory=list, max_length=64)
    mcp: list[Identifier] = Field(default_factory=list, max_length=32)
    attachments: list[dict[str, Any]] = Field(default_factory=list, max_length=16)
    notebook_references: list[dict[str, Any]] = Field(default_factory=list, max_length=32)
    question_notebook_references: list[StrictInt] = Field(default_factory=list, max_length=32)
    book_references: list[dict[str, Any]] = Field(default_factory=list, max_length=32)
    reading_references: list[dict[str, Any]] = Field(default_factory=list, max_length=32)
    history_references: list[Identifier] = Field(default_factory=list, max_length=32)
    memory_references: list[str] = Field(default_factory=list, max_length=16)
    persona: str | None = Field(default=None, max_length=100)
    workspace_mode: str | None = Field(default=None, max_length=64)
    mastery_path_id: str | None = Field(default=None, max_length=200)
    mastery_session_mode: str | None = Field(default=None, max_length=32)
    mastery_answer: dict[str, Any] | None = None
    mastery_skip: dict[str, Any] | None = None
    parent_message_id: StrictInt | None = None
    followup_question_context: dict[str, Any] | None = None
    selection_tutor_context: dict[str, Any] | None = None
    capability_once: bool = False
    auto_route: bool | None = None
    reading_material_id: str | None = Field(default=None, max_length=200)
    reading_material_revision: int | None = Field(default=None, ge=1)
    reading_workspace_id: str | None = Field(default=None, max_length=200)
    reading_viewport: dict[str, Any] | None = None
    timed_media_id: str | None = Field(default=None, max_length=200)
    timed_media_viewport: dict[str, Any] | None = None
    reply_language_override: str | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def bounded_options(self):
        # 数据结构在宿主限量；字段与资源归属由 worker 中原生 TurnRequest 再次验证。
        values = self.model_dump(include=set(NativeTurnOptions.model_fields))
        if len(json.dumps(values, ensure_ascii=False, allow_nan=False).encode()) > 24 * 1024 * 1024:
            raise ValueError("原生请求资源超过限制")
        return self


class NativeScopeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    student_id: Annotated[str, Field(min_length=1, max_length=64)]
    course_id: Annotated[str, Field(min_length=1, max_length=64)]
    course_title: Annotated[str, Field(min_length=1, max_length=60)]
    session_id: Annotated[str, Field(min_length=1, max_length=64)]


class MemoryOperation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['overview', 'read', 'write', 'delete_entry'] = 'overview'
    layer: Literal['L2', 'L3'] = 'L3'
    key: str = Field(default='preferences', min_length=1, max_length=64)
    content: str = Field(default='', max_length=2 * 1024 * 1024)
    entry_id: str = Field(default='', max_length=100)


class NativeMemoryRequest(NativeScopeRequest, MemoryOperation):
    pass


class NativeTurnKey(BaseModel):
    model_config = ConfigDict(extra="forbid")
    student_id: Annotated[str, Field(min_length=1, max_length=64)]
    course_id: Annotated[str, Field(min_length=1, max_length=64)]
    session_id: Annotated[str, Field(min_length=1, max_length=64)]
    request_id: Identifier
    task_id: Identifier
    task_revision: int = Field(ge=1)


class NativeTaskCheck(NativeTurnKey):
    memory_epoch: int = Field(ge=0)
    material_versions: dict[Identifier, Identifier] = Field(max_length=32)


class NativeTurnStart(NativeTaskCheck, NativeTurnOptions):
    course_title: str = Field(min_length=1, max_length=60)
    content: str = Field(min_length=1, max_length=4000)
    teaching_preferences: InteractionPreferences | None = None
    grounding: list[dict[str, Any]] = Field(default_factory=list, max_length=32)

    @field_validator("content")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("问题不能为空")
        return value

    def receipt_payload(self):
        # 新增字段的默认值不改变升级前已持久化收据的哈希。
        legacy = set(NativeTaskCheck.model_fields) | {"course_title", "content", "capability"}
        values = self.model_dump()
        defaults = NativeTurnOptions().model_dump()
        return {key: value for key, value in values.items()
                if key in legacy or (key == "teaching_preferences" and value is not None)
                or (key in defaults and value != defaults[key]) or (key == "grounding" and value)}


class NativeTurnCursor(NativeTurnKey):
    after_seq: int = Field(default=0, ge=0)


class NativeTurnCommand(NativeTurnKey):
    command_id: Identifier


class NativeTurnReply(NativeTurnCommand):
    text: str = Field(min_length=1, max_length=16000)


class NativeArtifactRequest(NativeTurnKey):
    item_id: Identifier
