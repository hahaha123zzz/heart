"""只允许已校验资源进入任务上下文；不存储新的学生能力判断。"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class ReaderLocation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    chapter_id: int = Field(ge=1, le=11)
    section_id: int = Field(ge=1)


class ExerciseTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    question_id: str = Field(min_length=1, max_length=64)
    part_id: str = Field(min_length=1, max_length=20)
    version: str = Field(pattern=r"^[a-f0-9]{64}$")


class TaskObject(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(min_length=1, max_length=180)
    kind: Literal["section", "pdf_selection", "exercise_part", "visualization", "truth_table", "relation"]
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(default="", max_length=1800)
    chapter_id: int = Field(ge=1, le=11)
    section_id: int = Field(ge=1)
    version: str = Field(default="", max_length=64)


class TaskContext(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1] = 1
    student_id: str = Field(min_length=1, max_length=64)
    session_id: str = Field(default="legacy", min_length=1, max_length=64)
    request_id: str | None = Field(default=None, min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=4000)
    knowledge_point: str = Field(default="", max_length=200)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=40)
    history_summary: str = Field(default="", max_length=4000)
    known_points: list[str] = Field(default_factory=list, max_length=20)
    objects: list[TaskObject] = Field(default_factory=list, max_length=4)
    preferences: dict[str, float] = Field(default_factory=dict)
    task_understanding_enabled: bool = True
    graph_snapshot: dict | None = None
    truth_table_snapshot: dict | None = None
    relation_snapshot: dict | None = None
    course_navigation: dict | None = None
    tutoring: dict = Field(default_factory=dict)

    def prompt_payload(self):
        # 识别无需知道学生ID，不把其作为模型生成引用的候选对象。
        payload = self.model_dump(exclude={"student_id", "session_id", "request_id", "task_understanding_enabled"})
        if payload.get('truth_table_snapshot'):
            payload['truth_table_snapshot'].pop('evaluation', None)
        if payload.get('relation_snapshot'):
            payload['relation_snapshot'].pop('evaluation',None)
        # Persist the private engine snapshot, but never send its answer keys
        # or cached evidence to intent/routing models.
        if payload.get('tutoring'):
            from agents.adaptive_tutoring import public_state
            payload['tutoring'] = public_state(payload['tutoring'])
        return payload
