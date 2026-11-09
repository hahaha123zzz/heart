"""只允许已校验资源进入任务上下文；不存储新的学生能力判断。"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr
from models.input_understanding import GroundedTurn, ObjectReference, ExecutionDecision, TurnRoute


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
    session_id: str = Field(default="legacy", min_length=1, max_length=100)
    request_id: str | None = Field(default=None, min_length=1, max_length=100)
    task_id: str | None = Field(default=None, max_length=100)
    task_revision: int | None = Field(default=None, ge=1)
    message: str = Field(min_length=1, max_length=4000)
    knowledge_point: str = Field(default="", max_length=200)
    history: list[dict[str, str]] = Field(default_factory=list)
    history_summary: str = ""
    _unified_context = PrivateAttr(default=None)

    @property
    def unified_context(self):
        from agents.turn_context import assemble_turn
        return assemble_turn(self)
    known_points: list[str] = Field(default_factory=list, max_length=20)
    objects: list[TaskObject] = Field(default_factory=list, max_length=4)
    current_object_ids: list[str] = Field(default_factory=list,max_length=4)
    preferences: dict[str, float] = Field(default_factory=dict)
    task_understanding_enabled: bool = True
    graph_snapshot: dict | None = None
    truth_table_snapshot: dict | None = None
    relation_snapshot: dict | None = None
    course_navigation: dict | None = None
    tutoring: dict = Field(default_factory=dict)
    selection_scope: dict | None = None
    session_study_plan: dict | None = None
    input_understanding: GroundedTurn | None = None
    input_mode: Literal['off', 'shadow', 'active'] = 'off'
    turn_route: dict | None = None
    activity_target: dict | None = None
    reference_objects: list[ObjectReference] = Field(default_factory=list, max_length=8)
    input_decision: ExecutionDecision | None = None

    def prompt_payload(self):
        # 识别无需知道学生ID，不把其作为模型生成引用的候选对象。
        payload = self.model_dump(exclude={"student_id", "session_id", "request_id", "task_understanding_enabled",
                                           "input_understanding", "input_mode", "turn_route", "activity_target",
                                           "current_object_ids", "reference_objects", "input_decision", "task_id",
                                           "task_revision"})
        if payload.get('truth_table_snapshot'):
            payload['truth_table_snapshot'].pop('evaluation', None)
        if payload.get('relation_snapshot'):
            payload['relation_snapshot'].pop('evaluation',None)
        # Persist the private engine snapshot, but never send its answer keys
        # or cached evidence to intent/routing models.
        if payload.get('tutoring'):
            from agents.adaptive_tutoring import public_state
            payload['tutoring'] = public_state(payload['tutoring'])
        if payload.get('session_study_plan'):
            payload['session_study_plan'].pop('student_id',None)
            payload['session_study_plan'].pop('session_id',None)
        return payload


def apply_route(context: TaskContext, route: TurnRoute) -> None:
    """Store the resolved turn route; chapter/section scope overrides stale cursors."""
    context.turn_route = route.model_dump()
    if route.scope not in ('chapter', 'section') or route.chapter_id is None:
        return
    context.activity_target = {
        'target_id': route.target_id or f'chapter:{route.chapter_id}',
        'name': route.name,
        'chapter_id': route.chapter_id,
        'section_id': route.section_id,
        'reason': 'turn_route:' + route.reason,
    }
    # A resolved chapter/section is authoritative for this turn; an old Q2
    # cursor would otherwise re-open the previous target.
    context.course_navigation = None
