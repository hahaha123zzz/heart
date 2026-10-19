"""任务识别结果；兼容既有流程字段，资源引用由服务端再核验。"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class RoutingResult(BaseModel):
    """业务失败状态与旧流程 intent 分开，防止异常被误认成继续学习。"""
    model_config = ConfigDict(extra="forbid", strict=True)

    status: Literal["ok", "unknown", "parse_error", "unavailable"] = "ok"
    student_move: Literal["question", "attempt", "statement", "acknowledgement", "off_task"] = "statement"
    move_status: Literal["", "adequate", "partial", "problematic"] = ""
    intent: Literal["continue", "switch_topic", "new_goal", "off_task", "clarify_task"] = "continue"
    topic: str = Field(default="", max_length=128)
    confidence: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)
    reason: str = Field(default="", max_length=1000)
    needs_context: bool = False

    @model_validator(mode="after")
    def check_move_status(self):
        if self.status == "ok":
            if self.student_move != "attempt" and self.move_status:
                raise ValueError("非 attempt 不得提供 move_status")
        return self

    @classmethod
    def failure(cls, status, reason):
        return cls(status=status, intent="clarify_task", confidence=0.0,
                   needs_context=True, reason=reason)


LearningIntent = Literal["explain", "proof", "example", "hint", "check_answer", "practice", "summary", "compare"]
AnswerConstraint = Literal["hint_only", "no_full_answer", "example_before_proof", "include_prerequisites", "verdict_only", "no_questions"]
MissingSlot = Literal["target", "task", "topic", "answer_format"]


class TaskUnderstanding(RoutingResult):
    schema_version: Literal[1] = 1
    learning_intents: list[LearningIntent] = Field(default_factory=list, max_length=3)
    target_refs: list[str] = Field(default_factory=list, max_length=4)
    answer_constraints: list[AnswerConstraint] = Field(default_factory=list, max_length=4)
    missing_slots: list[MissingSlot] = Field(default_factory=list, max_length=4)
    rewritten_query: str = Field(default="", max_length=4000)
    rewrite_sources: list[str] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def unique_values(self):
        for field in ("learning_intents", "target_refs", "answer_constraints", "missing_slots", "rewrite_sources"):
            values = getattr(self, field)
            if len(values) != len(set(values)):
                raise ValueError("任务字段包含重复值")
        if self.missing_slots and self.status == "ok" and self.intent != "clarify_task":
            raise ValueError("缺少必要槽位时必须澄清")
        return self
