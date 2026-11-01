"""六维只读视图（psy-6d-v1）。

只读已校验的 GroundedTurn 与任务上下文：不调模型、不读库、不写业务状态。
D1/D4/D5/D6 全部由现有字段推导；D2 与 D3 的 classifiable 标签来自上游
annotations（规则或模型），缺失即为弃权，不补 unknown。
"""
from __future__ import annotations

import json
import os

_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "knowledge",
    "semantic_labels.v1.json",
)

TEXTBOOK_KINDS = {"pdf_selection", "figure", "text_block"}

# Action -> D1。未列出的动作一律 unclear，防止新增动作绕过分流。
ACTION_INTENT = {
    "discuss_claim": "repair",
    "submit_student_answer": "exercise_interaction",
    "request_practice": "exercise_interaction",
    "resume_pending_question": "learning_management",
    "resume_learning_activity": "learning_management",
    "propose_learning_plan": "learning_management",
    "revise_learning_plan": "learning_management",
    "confirm_learning_plan": "learning_management",
    "switch_learning_target": "learning_management",
    "propose_preference_change": "session_control",
    "clarify_reference": "unclear",
}

_EMPTY_FIELD = {"value": None, "source": None}


def registry() -> dict:
    try:
        with open(_PATH, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def version() -> str | None:
    return registry().get("version")


def labels() -> dict:
    return registry().get("labels") or {}


def valid_label(dimension: str, label: str) -> bool:
    """注册表是标签的唯一权威；未知维度或取值一律拒绝。"""
    if dimension not in labels():
        return False
    data = registry().get("dimensions", {})
    if dimension == "cognitive_demand":
        values = data.get("cognitive_demand", {}).get("values") or {}
    else:
        values = (data.get("learner_state", {}).get("fields", {})
                  .get(dimension, {}).get("values") or [])
    return label in values


def missing_labels(turn) -> list[str]:
    """尚未标注的可分类维度；调用方只把它们作为待补维度传给分类端口。"""
    present = {row.dimension for row in turn.annotations}
    return [name for name in labels() if name not in present]


def intent_for(action: str, *, has_pending: bool = False, ref_kind: str | None = None) -> str:
    if action in ("explain_content", "compare_content"):
        return "textbook_interaction" if ref_kind in TEXTBOOK_KINDS else "knowledge_query"
    if action == "provide_hint":
        return "exercise_interaction" if has_pending else "repair"
    return ACTION_INTENT.get(action, "unclear")


def build(turn, context=None) -> dict:
    """六维视图。缺数据写 null，不推断学生能力。"""
    pending = _pending(context)
    annotated = _group(turn)
    support = _support(turn, context)
    return {
        "ontology_version": version(),
        "request_intent": _intent(turn, pending),
        "cognitive_demand": _label_view(annotated, "cognitive_demand"),
        "learner_state": _learner(turn, context, annotated, pending),
        "content_target": _target(turn, context),
        "support_need": support,
        "teaching_stage": _stage(turn, context, annotated, pending, support),
    }


def _pending(context) -> bool:
    progress = ((getattr(context, "tutoring", None) or {}).get("progress") or {}) if context else {}
    return bool(progress.get("pending_question"))


def _group(turn) -> dict:
    grouped = {}
    for row in turn.annotations:
        grouped.setdefault(row.dimension, []).append(row)
    return grouped


def _label_view(annotated: dict, name: str) -> dict:
    rows = annotated.get(name) or []
    values = list(dict.fromkeys(row.label for row in rows))
    sources = {row.source for row in rows}
    return {"values": values, "source": next(iter(sources)) if len(sources) == 1 else
            ("mixed" if sources else None)}


def _field(annotated: dict, name: str) -> dict:
    view = _label_view(annotated, name)
    values = view["values"]
    if not values:
        return dict(_EMPTY_FIELD)
    return {"value": values if len(values) > 1 else values[0], "source": view["source"]}


def _intent(turn, pending: bool) -> dict:
    refs = {row.ref_id: row for row in turn.references}
    values = []
    for task in turn.tasks:
        ref = refs.get(task.target_ref) if task.target_ref else None
        value = intent_for(task.action, has_pending=pending,
                           ref_kind=getattr(ref, "kind", None))
        if value not in values:
            values.append(value)
    return {"values": values, "primary": values[0] if values else "unclear", "source": "derive"}


def _learner(turn, context, annotated: dict, pending: bool) -> dict:
    return {
        "attempt": {"value": _attempt(turn, context, pending), "source": "state"},
        "self_report": _field(annotated, "self_report"),
        "difficulty_locus": _field(annotated, "difficulty_locus"),
        "engagement": _field(annotated, "engagement"),
        # TaskContext 不携带 StudentState；接记忆层后再填，先保留 null。
        "affect": dict(_EMPTY_FIELD),
        "history": dict(_EMPTY_FIELD),
    }


def _attempt(turn, context, pending: bool) -> str:
    assessment = ((getattr(context, "tutoring", None) or {}).get("assessment") or {}) if context else {}
    verdict = assessment.get("verdict") if isinstance(assessment, dict) else None
    if verdict in ("correct", "incorrect", "partial"):
        return verdict
    if pending:
        return "awaiting"
    return "none"


def _target(turn, context) -> dict:
    refs = {row.ref_id: row for row in turn.references}
    objects = []
    for task in turn.tasks:
        ref = refs.get(task.target_ref) if task.target_ref else None
        if ref is not None:
            # 只暴露本轮引用别名与类型；canonical_id 属于内部身份，不进对外摘要。
            objects.append({"ref_id": ref.ref_id, "kind": ref.kind, "status": ref.status})
    activity = (getattr(context, "activity_target", None) or {}) if context else {}
    chapter = activity.get("chapter_id") if context else None
    if chapter is None and context is not None:
        chapter = next((obj.chapter_id for obj in getattr(context, "objects", []) or []), None)
    knowledge_point = None
    if context is not None:
        knowledge_point = getattr(context, "knowledge_point", "") or activity.get("target_id") or None
    return {
        "objects": objects,
        "knowledge_point_id": knowledge_point,
        "chapter_id": chapter,
        "section_id": activity.get("section_id"),
        "source": "read",
    }


def _support(turn, context) -> dict:
    preferences = dict(getattr(context, "preferences", None) or {}) if context else {}
    turn_values = {}
    for directive in turn.directives:
        if directive.scope in ("turn", "question", "session_plan"):
            turn_values.setdefault(directive.key, directive.value)
    constraints = {constraint for task in turn.tasks for constraint in task.constraints}

    verbosity, verbosity_source = _pick(turn_values, preferences, "answer_length", ("short", "normal", "long"))
    guidance = None
    guidance_source = None
    style = turn_values.get("response_style")
    if style in ("direct", "guided"):
        guidance, guidance_source = ("direct" if style == "direct" else "strong"), "turn"
    elif "teaching_sequence" in preferences:
        sequence = preferences["teaching_sequence"]
        guidance = "direct" if sequence > 0.66 else "light" if sequence < 0.34 else None
        guidance_source = "profile" if guidance else None
    examples, examples_source = _pick(turn_values, preferences, "example_density", ("none", "one", "many"))

    disclosure = ("no_answer" if "no_full_answer" in constraints else
                  "hint_only" if "hint_only" in constraints else
                  "verdict_only" if "verdict_only" in constraints else "full")
    return {
        "verbosity": {"value": verbosity, "source": verbosity_source},
        "terminology": dict(_EMPTY_FIELD),
        "guidance": {"value": guidance, "source": guidance_source},
        "examples": {"value": examples, "source": examples_source},
        "modality": dict(_EMPTY_FIELD),
        # 披露是约束契约，不由偏好标量推断。
        "disclosure": {"value": disclosure, "source": "constraint"},
        "difficulty": dict(_EMPTY_FIELD),
    }


def _pick(turn_values: dict, preferences: dict, key: str, levels: tuple) -> tuple:
    value = turn_values.get(key)
    source = "turn" if value is not None else None
    if value is None and key in preferences:
        value, source = preferences[key], "profile"
    if not isinstance(value, (int, float)):
        return None, None
    return (levels[0] if value < 0.34 else levels[2] if value > 0.66 else levels[1]), source


def _stage(turn, context, annotated: dict, pending: bool, support: dict) -> dict:
    tutoring = (getattr(context, "tutoring", None) or {}) if context else {}
    engagement = (_field(annotated, "engagement")["value"])
    actions = [task.action for task in turn.tasks]
    if engagement == "skip" or (engagement == "answer_seeking"
                                and support["disclosure"]["value"] != "full"):
        turn_state = "closing"
    elif "request_practice" in actions:
        turn_state = "practicing"
    elif any(action in ("explain_content", "compare_content", "provide_hint", "discuss_claim")
             for action in actions):
        turn_state = "explaining"
    else:
        turn_state = "awaiting_student"
    return {
        "stage": tutoring.get("stage"),
        "turn_state": turn_state,
        "next": "close" if turn_state == "closing" else
                "continue_pending" if pending else "advance",
        "source": "state|derive",
    }
