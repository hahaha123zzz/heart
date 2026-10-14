"""固定双变量真值表；客户端不传公式答案或学习能力标签。"""
from typing import Literal
from pydantic import Field, model_validator
from models.visualization import Scope, StrictModel

Template = Literal['and', 'or', 'implies', 'equivalent', 'not-or']


class CreateTruthTable(Scope):
    request_id: str = Field(min_length=1, max_length=64)
    expected_epoch: int = Field(ge=0)
    template_id: Template = 'implies'
    mode: Literal['explore', 'assessment'] = 'assessment'
    correction_of: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode='after')
    def correction_mode(self):
        if self.correction_of and self.mode != 'assessment':
            raise ValueError('订正仅用于测评')
        return self


class TableAnswers(Scope):
    request_id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)
    values: dict[str, bool | None] = Field(min_length=4, max_length=4)
    explanation: str = Field(default='', max_length=1200)


class TruthTableTarget(StrictModel):
    artifact_id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)
    row_id: Literal['00', '01', '10', '11']
    action: Literal['hint', 'explain'] | None = None
