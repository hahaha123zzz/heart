"""Deterministic first-pass interaction router.

This is intentionally small and conservative. It recognizes explicit student
requests before considering the current teaching state. Unrecognized input
falls back to the existing teaching flow, which keeps rollout backwards
compatible. A model-backed classifier can replace this implementation behind
the same ``route_interaction`` contract later.
"""

import re

from .contracts import AgentContext, IntentDecision, InteractionIntent


_RULES: tuple[tuple[InteractionIntent, tuple[str, ...], bool], ...] = (
    ("pause", ("暂停", "先停一下", "稍后再学", "不想继续"), True),
    ("summarize", ("总结一下", "小结一下", "帮我总结", "总结本节"), True),
    ("review", ("复习", "再回顾", "回顾上一", "重新讲一遍"), True),
    ("practice", ("练习", "做题", "给我一道题", "测试我"), True),
    ("ask_hint", ("提示", "给点提示", "我不会", "没懂", "不知道", "不懂", "没听懂", "不清楚", "看不懂", "没思路", "从零开始"), True),
    ("change_topic", ("换个话题", "换一个知识点", "换个例子", "跳过这个"), True),
    ("ask_question", ("为什么", "怎么理解", "是什么意思", "有什么区别", "解释一下"), True),
)


def _normalized(text: str) -> str:
    return re.sub(r"\s+", "", text.strip().lower())


def route_interaction(context: AgentContext) -> IntentDecision:
    """Route explicit student intent without mutating teaching state.

    The first matching explicit rule wins. The output includes the rule name so
    telemetry and later evaluation can distinguish routing from teaching errors.
    """

    text = _normalized(context.student_text)
    if not text:
        return IntentDecision(
            intent="continue_teaching",
            confidence=0.0,
            reason="empty_input_falls_back_to_current_flow",
        )

    for intent, phrases, interrupt in _RULES:
        if any(phrase in text for phrase in phrases):
            return IntentDecision(
                intent=intent,
                confidence=0.95,
                reason="explicit_student_request",
                matched_rule=intent,
                interrupt_current_flow=interrupt,
            )

    return IntentDecision(
        intent="continue_teaching",
        confidence=0.45,
        reason="no_explicit_intent_detected",
        interrupt_current_flow=False,
    )
