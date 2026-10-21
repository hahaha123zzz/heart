"""API请求模型独立于应用启动，便于无副作用测试。"""
from typing import Literal
from pydantic import BaseModel, Field, model_validator
from knowledge.pdf_reader import PDFSelection
from models.task_context import ReaderLocation, ExerciseTarget
from models.visualization import VisualizationTarget
from models.truth_table import TruthTableTarget
from models.relation import RelationTarget
from models.interaction_preferences import InteractionPreferences


class ChatRequest(BaseModel):
    student_id: str = Field(default="default", min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=4000)
    learning_goal: str | None = Field(default=None, max_length=200)
    account_type: str = "test"
    selection: PDFSelection | None = None
    reader_location: ReaderLocation | None = None
    exercise_target: ExerciseTarget | None = None
    exercise_help: Literal['hint', 'explain'] | None = None
    exercise_hint_level: int = Field(default=1, ge=1, le=3)
    visualization_target: VisualizationTarget | None = None
    truth_table_target: TruthTableTarget | None = None
    relation_target: RelationTarget | None = None
    session_id: str = Field(default="legacy", min_length=1, max_length=64)
    request_id: str | None = Field(default=None, min_length=1, max_length=64)
    style_overrides: InteractionPreferences | None = None

    task_id: str | None = Field(default=None, min_length=1, max_length=64)
    task_revision: int | None = Field(default=None, ge=1)
    selected_option: str | None = Field(default=None, min_length=1, max_length=180)

    @model_validator(mode="after")
    def one_explicit_object(self):
        if self.exercise_help is not None and self.exercise_target is None:
            raise ValueError('练习帮助必须指定小题')
        if sum(x is not None for x in (self.selection, self.exercise_target, self.visualization_target, self.truth_table_target, self.relation_target)) > 1:
            raise ValueError("教材选区、练习小题、互动图和真值表请分别提问")
        if (self.task_id is None) != (self.task_revision is None):
            raise ValueError("task_id和task_revision必须一起提供")
        if self.selected_option is not None and self.task_id is None:
            raise ValueError("选择澄清选项必须提供task_id")
        return self
