"""宿主私有原生运行时契约；身份、版本与资源由宿主填写。"""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Identifier = Annotated[str, Field(min_length=1, max_length=100)]


class NativeTurnKey(BaseModel):
    model_config = ConfigDict(extra='forbid')
    student_id: Annotated[str, Field(min_length=1, max_length=64)]
    course_id: Annotated[str, Field(min_length=1, max_length=64)]
    session_id: Annotated[str, Field(min_length=1, max_length=64)]
    request_id: Identifier
    task_id: Identifier
    task_revision: int = Field(ge=1)


class NativeTurnStart(NativeTurnKey):
    course_title: str = Field(min_length=1, max_length=60)
    content: str = Field(min_length=1, max_length=4000)
    capability: Literal['chat', 'ask_questions'] = 'chat'
    memory_epoch: int = Field(ge=0)
    material_versions: dict[Identifier, Identifier] = Field(max_length=32)

    @field_validator('content')
    @classmethod
    def nonblank(cls, value):
        if not value.strip(): raise ValueError('问题不能为空')
        return value


class NativeTurnCursor(NativeTurnKey):
    after_seq: int = Field(default=0, ge=0)


class NativeTurnCommand(NativeTurnKey):
    command_id: Identifier


class NativeTurnReply(NativeTurnCommand):
    text: str = Field(min_length=1, max_length=16000)
