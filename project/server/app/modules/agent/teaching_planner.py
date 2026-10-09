"""Pure teaching planner for the first shared-agent slice."""

from dataclasses import dataclass
from typing import Literal

from .contracts import AgentContext, IntentDecision
from .teaching_plan import ShortTermTeachingPlan


TeachingAction = Literal[
    "continue_current_step", "answer_question", "give_hint", "change_topic",
    "start_review", "start_practice", "summarize", "pause",
    "review_prerequisite", "check_understanding", "advance_step",
]


@dataclass(frozen=True)
class TeachingDecision:
    action: TeachingAction
    reason: str
    plan_step_id: str | None = None
    interrupt_current_flow: bool = False


def plan_teaching_action(
    context: AgentContext,
    intent: IntentDecision,
    plan: ShortTermTeachingPlan | None = None,
) -> TeachingDecision:
    feedback = context.metadata.get("feedback_kind")
    evaluation = context.metadata.get("answer_evaluation")
    stuck_count = context.metadata.get("stuck_count", 0)
    if feedback == "stuck" or evaluation in ("incorrect", "partial"):
        action: TeachingAction = "review_prerequisite" if stuck_count >= 2 else "give_hint"
        return TeachingDecision(
            action=action,
            reason="student_stuck_or_incorrect",
            plan_step_id=plan.current_step.id if plan else None,
            interrupt_current_flow=True,
        )
    if feedback == "understood" or evaluation == "uncertain":
        return TeachingDecision(
            action="check_understanding",
            reason="self_report_needs_check" if feedback == "understood" else "answer_not_verifiable",
            plan_step_id=plan.current_step.id if plan else None,
        )
    if evaluation == "correct":
        return TeachingDecision(
            action="advance_step",
            reason="provisionally_assessed_answer",
            plan_step_id=plan.current_step.id if plan else None,
        )
    direct_actions: dict[str, TeachingAction] = {
        "ask_question": "answer_question",
        "ask_hint": "give_hint",
        "change_topic": "change_topic",
        "review": "start_review",
        "practice": "start_practice",
        "summarize": "summarize",
        "pause": "pause",
    }
    action = direct_actions.get(intent.intent)
    if action is not None:
        return TeachingDecision(
            action=action,
            reason=f"routed_intent:{intent.intent}",
            plan_step_id=plan.current_step.id if plan else None,
            interrupt_current_flow=intent.interrupt_current_flow,
        )
    return TeachingDecision(
        action="continue_current_step",
        reason="no_interrupting_intent",
        plan_step_id=plan.current_step.id if plan else None,
    )
