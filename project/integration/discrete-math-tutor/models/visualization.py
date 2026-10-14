"""受控图规格与操作；不接受客户端算法结论或执行代码。"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class GraphNode(StrictModel):
    id: str = Field(pattern=r'^v[1-9][0-9]?$', max_length=3)
    label: str = Field(min_length=1, max_length=12)


class GraphEdge(StrictModel):
    source: str = Field(pattern=r'^v[1-9][0-9]?$', max_length=3)
    target: str = Field(pattern=r'^v[1-9][0-9]?$', max_length=3)


class GraphSpec(StrictModel):
    nodes: list[GraphNode] = Field(min_length=1, max_length=12)
    edges: list[GraphEdge] = Field(max_length=30)

    @model_validator(mode='after')
    def simple_graph(self):
        ids = [node.id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError('顶点 ID 重复')
        seen = set()
        for edge in self.edges:
            if edge.source not in ids or edge.target not in ids:
                raise ValueError('边引用未知顶点')
            if edge.source == edge.target:
                raise ValueError('首版不支持自环')
            pair = tuple(sorted((edge.source, edge.target)))
            if pair in seen:
                raise ValueError('首版不支持重复边')
            seen.add(pair)
        self.edges = [GraphEdge(source=a, target=b) for a, b in sorted(seen)]
        return self


class Position(StrictModel):
    x: FiniteFloat = Field(ge=-10000, le=10000)
    y: FiniteFloat = Field(ge=-10000, le=10000)


class Scope(StrictModel):
    student_id: str = Field(min_length=1, max_length=64, pattern=r'^[^\r\n\t]+$')
    session_id: str = Field(min_length=1, max_length=64, pattern=r'^[^\r\n\t]+$')


class CreateVisualization(Scope):
    request_id: str = Field(min_length=1, max_length=64)
    expected_epoch: int = Field(ge=0)
    template_id: Literal['euler-cycle-v1'] = 'euler-cycle-v1'
    graph: GraphSpec | None = None
    mode: Literal['explore', 'hint', 'assessment'] = 'explore'
    correction_of: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode='after')
    def assessment_seed(self):
        if self.correction_of and (self.mode != 'assessment' or self.graph is not None):
            raise ValueError('订正只能引用已提交的测评图，不能上传图')
        if self.mode == 'assessment' and self.graph is not None:
            raise ValueError('测评图由服务端出题，不能上传已知答案的图')
        return self


class GraphSubmission(Scope):
    request_id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)
    degrees: dict[str, int] = Field(min_length=1, max_length=12)
    connected: bool
    prediction: Literal['circuit', 'open_path', 'neither']
    explanation: str = Field(default='', max_length=1200)

    @model_validator(mode='after')
    def bounded_degrees(self):
        if any(isinstance(value, bool) or not 0 <= value <= 11 for value in self.degrees.values()):
            raise ValueError('度数需为 0 至 11 的整数')
        return self


class VisualizationTarget(StrictModel):
    artifact_id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)
    action: Literal['explain', 'hint'] | None = None


class GraphOperation(Scope):
    request_id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)
    operation: Literal['add_edge', 'remove_edge', 'layout']
    source: str | None = Field(default=None, pattern=r'^v[1-9][0-9]?$', max_length=3)
    target: str | None = Field(default=None, pattern=r'^v[1-9][0-9]?$', max_length=3)
    positions: dict[str, Position] | None = None
    expected_layout_revision: int | None = Field(default=None, ge=1)

    @model_validator(mode='after')
    def operation_fields(self):
        if self.operation == 'layout':
            if self.positions is None or self.expected_layout_revision is None or self.source or self.target:
                raise ValueError('布局操作需提供位置与布局版本')
            if len(self.positions) > 12:
                raise ValueError('位置超过顶点上限')
        elif not self.source or not self.target or self.positions is not None or self.expected_layout_revision is not None:
            raise ValueError('边操作只能指定两个端点')
        return self
