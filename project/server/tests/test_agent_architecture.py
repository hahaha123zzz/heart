from app.modules.agent.contracts import AgentContext, StudentState
from app.modules.agent.demo_learning import DemoLearningSession, classify_feedback
from app.modules.agent.intent_router import route_interaction
from app.modules.agent.teaching_plan import PlanStep, ShortTermTeachingPlan
from app.modules.agent.teaching_planner import plan_teaching_action
from app.modules.agent.student_state import StudentSignal, build_student_state


def _plan() -> ShortTermTeachingPlan:
    return ShortTermTeachingPlan(
        id="plan-1",
        knowledge_point_id="kp-1",
        steps=(
            PlanStep("step-1", "diagnose", "has_initial_response"),
            PlanStep("step-2", "teach", "student_can_explain"),
            PlanStep("step-3", "check", "answer_quality >= 0.7"),
        ),
    )


def test_explicit_student_request_interrupts_current_flow() -> None:
    decision = route_interaction(
        AgentContext(student_text="先暂停一下，我想复习上一节")
    )

    assert decision.intent == "pause"
    assert decision.interrupt_current_flow is True
    assert decision.reason == "explicit_student_request"


def test_unknown_input_keeps_backward_compatible_fallback() -> None:
    decision = route_interaction(AgentContext(student_text="我觉得这个例子有点奇怪"))

    assert decision.intent == "continue_teaching"
    assert decision.interrupt_current_flow is False


def test_planner_keeps_routing_separate_from_execution() -> None:
    context = AgentContext(
        student_text="给我一点提示",
        student_state=StudentState(mastery=0.2, confidence=0.3),
    )
    intent = route_interaction(context)
    decision = plan_teaching_action(context, intent, _plan())

    assert decision.action == "give_hint"
    assert decision.plan_step_id == "step-1"
    assert decision.interrupt_current_flow is True


def test_short_term_plan_is_bounded() -> None:
    plan = _plan()

    assert len(plan.steps) == 3
    assert plan.current_step.step_type == "diagnose"


def test_student_state_aggregates_evidence_without_filling_unknowns() -> None:
    state = build_student_state(
        [
            StudentSignal(
                knowledge_point_id="kp-1",
                mastery=0.4,
                confidence=0.2,
                misconception="把相关和因果混淆",
                emotion="confused",
                source_ref="event-1",
            ),
            StudentSignal(
                knowledge_point_id="kp-1",
                mastery=0.8,
                confidence=0.6,
                metacognition=0.5,
                source_ref="event-2",
                weight=2,
            ),
        ],
        preferences={"response_length": "CONCISE"},
    )

    assert round(state.mastery, 3) == 0.667
    assert round(state.confidence, 3) == 0.467
    assert state.misconceptions == ("把相关和因果混淆",)
    assert state.metacognition == 0.5
    assert state.emotion == "confused"
    assert state.evidence_refs == ("event-1", "event-2")


def test_student_state_does_not_invent_a_mastery_score() -> None:
    state = build_student_state([StudentSignal(source_ref="event-1")])

    assert state.mastery is None
    assert state.confidence is None


def test_not_knowing_interrupts_teaching_without_inventing_mastery() -> None:
    session = DemoLearningSession()
    progress = session.activate("图｜路径与回路", "路径与回路")
    progress.record_reply("这个上界是 n 还是 n-1？")
    assert classify_feedback("不知道", awaiting_answer=True) == "stuck"

    kind = progress.observe("不知道")
    context = AgentContext(
        student_text="不知道", student_state=progress.student_state,
        metadata={"feedback_kind": kind, "stuck_count": progress.stuck_count},
    )
    decision = plan_teaching_action(context, route_interaction(context), progress.plan)
    assert decision.action == "give_hint"
    assert progress.student_state.mastery is None
    assert progress.plan.current_step.id == "teach"

    kind = progress.observe("还是不知道")
    context = AgentContext(
        student_text="还是不知道", student_state=progress.student_state,
        metadata={"feedback_kind": kind, "stuck_count": progress.stuck_count},
    )
    decision = plan_teaching_action(context, route_interaction(context), progress.plan)
    assert decision.action == "review_prerequisite"


def test_self_report_is_not_mastery_but_verified_answer_advances() -> None:
    session = DemoLearningSession()
    progress = session.activate("图｜路径与回路", "路径与回路")
    progress.observe("懂了")
    assert progress.student_state.mastery is None
    context = AgentContext(
        student_text="懂了", student_state=progress.student_state,
        metadata={"feedback_kind": "understood"},
    )
    assert plan_teaching_action(context, route_interaction(context), progress.plan).action == "check_understanding"

    progress.record_reply("闭路径的起点和终点是否相同？")
    progress.observe("相同", evaluation="correct")
    assert progress.student_state.mastery == 0.6
    assert progress.plan.current_step.id == "teach"
    session.reset()
    assert session.active is None
    assert not session.topics


def test_topic_progress_is_isolated_and_explicit_commands_are_not_answers() -> None:
    session = DemoLearningSession()
    graph = session.activate("图｜基本概念", "图")
    graph.observe("不知道")
    graph.record_reply("什么是顶点？")
    assert classify_feedback("换个话题", awaiting_answer=True) == "other"

    sets = session.activate("集合｜基本概念", "集合")
    assert sets.stuck_count == 0
    assert sets.student_state.confidence is None
    assert session.activate("图｜基本概念", "图").stuck_count == 1
