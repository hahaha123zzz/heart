"""固定三元素关系，保留有向序偶与自环。"""
from typing import Literal
from pydantic import Field, model_validator
from models.visualization import Scope, StrictModel, Position

Element = Literal['a', 'b', 'c']
Property = Literal['reflexive', 'irreflexive', 'symmetric', 'antisymmetric', 'transitive']
ClosureKind = Literal['reflexive', 'symmetric', 'transitive']


class ClosureFocus(StrictModel):
    kind: ClosureKind
    step: int = Field(ge=0,le=9)


class ClosurePreview(Scope):
    expected_revision: int = Field(ge=1)
    kind: ClosureKind


class RelationPair(StrictModel):
    source: Element
    target: Element


class RelationSpec(StrictModel):
    pairs: list[RelationPair] = Field(max_length=9)

    @model_validator(mode='after')
    def unique_pairs(self):
        pairs = [(pair.source,pair.target) for pair in self.pairs]
        if len(set(pairs)) != len(pairs):
            raise ValueError('关系中不能重复保存同一个序偶')
        self.pairs = [RelationPair(source=a,target=b) for a,b in sorted(pairs)]
        return self


class CreateRelation(Scope):
    request_id: str = Field(min_length=1, max_length=64)
    expected_epoch: int = Field(ge=0)
    template_id: Literal['r1','r2','r3','r4','r5'] = 'r3'
    mode: Literal['explore','assessment'] = 'explore'
    correction_of: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode='after')
    def correction_mode(self):
        if self.correction_of and self.mode != 'assessment':
            raise ValueError('订正只能用于测评')
        return self


class RelationAnswers(Scope):
    request_id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)
    values: dict[Property, bool | None] = Field(min_length=5, max_length=5)
    explanation: str = Field(default='', max_length=1200)


class RelationOperation(Scope):
    request_id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)
    operation: Literal['set_pair','layout']
    pair: RelationPair | None = None
    present: bool | None = None
    positions: dict[Element, Position] | None = None
    expected_layout_revision: int | None = Field(default=None, ge=1)

    @model_validator(mode='after')
    def fields_for_operation(self):
        if self.operation == 'set_pair':
            if self.pair is None or self.present is None or self.positions is not None or self.expected_layout_revision is not None:
                raise ValueError('关系修改必须明确序偶及是否存在')
        elif self.pair is not None or self.present is not None or self.positions is None or self.expected_layout_revision is None or set(self.positions) != {'a','b','c'}:
            raise ValueError('布局必须包含 a、b、c 及布局版本')
        return self


class RelationTarget(StrictModel):
    artifact_id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)
    property: Property = 'transitive'
    pair: RelationPair | None = None
    action: Literal['hint','explain'] | None = None
    closure: ClosureFocus | None = None

    @model_validator(mode='after')
    def closure_property(self):
        if self.closure and self.property != self.closure.kind:
            raise ValueError('闭包类型必须与所选性质一致')
        return self
