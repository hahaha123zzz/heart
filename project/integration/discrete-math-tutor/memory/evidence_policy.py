"""学生观测与状态投影分离：借鉴知识追踪，不把提问等同测量。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvidenceDecision:
    independent: bool
    eligible: bool
    reason: str
    verification: str = "ai_provisional"


def assess_graph_attempt(assisted: bool) -> EvidenceDecision:
    """规则只能验证结构化作答；不能由点击次数或自由解释推断掌握度。"""
    return EvidenceDecision(not assisted, not assisted,
        '使用过提示或解释，按辅助作答记录' if assisted else '新测评图上的独立结构化作答',
        verification='rule_verified')


def source_quote(item, student_input: str) -> str:
    quote = str(getattr(item, "source_quote", "") or "").strip()
    if not quote:
        # 兼容旧结构：只有内容就是原文时才能作为来源。
        quote = str(getattr(item, "content", "") or "").strip()
    return quote if quote and quote in student_input else ""


def assess_attempt(routing, message, evidence, previous_event=None, has_history=False, blocked=False):
    if blocked or routing.student_move != "attempt":
        return EvidenceDecision(False, False, "本轮为提问、讲解或自述，未测量独立能力")
    if routing.confidence < .7:
        return EvidenceDecision(False, False, "作答类别尚不确定")
    previous = (previous_event or {}).get("payload", {})
    assisted = previous.get("instructional_move") in (
        "worked_example", "direct_explanation", "hint", "give_hint", "progressive_hinting", "scaffold", "scaffolding", "guided_revision", "summarization")
    assisted = assisted or previous.get("teaching_context", {}).get("feedback_mode") in (
        "targeted_hint", "hint_only", "worked_example", "supportive_hint", "explain_feedback", "confirm_and_reflect", "check_self_report", "verdict_only")
    assisted = assisted or (has_history and previous_event is None)
    if assisted:
        return EvidenceDecision(False, False, "此前提供讲解或提示，本次按辅助作答记录")
    grounded = any(getattr(e, "evidence_type", "") in (
        "conceptual_understanding", "partial", "misconception") and source_quote(e, message) for e in evidence)
    return EvidenceDecision(True, grounded, "独立作答原文可追溯" if grounded else "缺少学生原文证据")


def project_state(before, candidate, raw, decision):
    """同轮只融合一次；保留暂定估计，步骤推进另检查实际累计值。"""
    state = candidate.model_copy(deep=True)
    state.current_concept = before.current_concept
    state.mastery = before.mastery
    state.steps_mastery = dict(before.steps_mastery)
    state.confidence = before.confidence
    state.metacognition = before.metacognition
    updates = dict(raw)
    if not decision.eligible:
        updates.pop("mastery", None)
        updates.pop("steps_mastery", None)
        state.misconception = before.misconception
        state.remaining_gap = before.remaining_gap
        state.mistake_patterns = [p.model_copy(deep=True) for p in before.mistake_patterns]
    state.blend_numeric(updates, alpha=.4)
    return state
