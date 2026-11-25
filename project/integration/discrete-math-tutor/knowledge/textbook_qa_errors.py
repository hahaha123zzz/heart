"""Error taxonomy for textbook-only QA evaluation."""

from __future__ import annotations

from dataclasses import dataclass


ERROR_LABELS = (
    "correct",
    "wrong_route_refusal",
    "wrong_route_answer",
    "clarification_missing",
    "invalid_citation",
    "retrieval_miss",
    "wrong_citation",
    "wrong_concept",
    "incomplete_condition",
    "unsupported_claim",
    "external_content",
)


@dataclass(frozen=True)
class ErrorDecision:
    label: str
    reason: str


def classify_error(checks: dict) -> ErrorDecision:
    """Choose one primary error, ordered by user impact."""
    if not checks.get("route_correct"):
        if checks.get("expected_route") == "answer":
            return ErrorDecision("wrong_route_refusal", "应回答但未回答")
        if checks.get("expected_route") == "clarify":
            return ErrorDecision("clarification_missing", "应澄清但没有要求补充对象")
        return ErrorDecision("wrong_route_answer", "应拒答却继续回答")
    if checks.get("invalid_citation"):
        return ErrorDecision("invalid_citation", "引用位置或原文无效")
    if checks.get("expected_route") != "answer":
        return ErrorDecision("correct", "路由和拒答符合预期")
    if not checks.get("retrieval_hit"):
        return ErrorDecision("retrieval_miss", "没有命中预期教材小节")
    if checks.get("wrong_citation"):
        return ErrorDecision("wrong_citation", "引用了预期小节之外的错误来源")
    if not checks.get("concept_hit"):
        return ErrorDecision("wrong_concept", "回答没有识别预期教材概念")
    if not checks.get("required_groups_hit"):
        return ErrorDecision("incomplete_condition", "定义、条件或定理结论不完整")
    if not checks.get("support_groups_hit"):
        return ErrorDecision("unsupported_claim", "回答结论未被引用原文覆盖")
    if checks.get("external_content"):
        return ErrorDecision("external_content", "回答加入教材外内容")
    return ErrorDecision("correct", "教材问答符合预期")
