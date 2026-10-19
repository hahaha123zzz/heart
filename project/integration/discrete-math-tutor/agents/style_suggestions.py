"""复用本轮教学诊断提出建议；这里只返回选项，不能保存偏好。"""
from agents.learning_feedback import is_stuck


def suggest_style(result, context, recent):
    if result.get("answer_status") != "answered" or context.preferences.get("style_suggestions", 1) < .34:
        return None
    previous = next((row for row in reversed(recent) if row.get("result", {}).get("answer_status") == "answered"), None)
    if not previous or previous.get("knowledge_point") != result.get("knowledge_point"):
        return None
    feedback = result.get("teaching_feedback", {}).get("mode")
    old_feedback = previous["result"].get("teaching_feedback", {}).get("mode")
    repeated_difficulty = feedback in {"targeted_hint", "supportive_hint", "worked_example"} and old_feedback in {"targeted_hint", "supportive_hint", "worked_example"}
    repeated_stuck = is_stuck(context.message) and is_stuck(previous.get("payload", {}).get("message", ""))
    if not (repeated_difficulty or repeated_stuck):
        return None
    values = {key: value for key, value in {"learning_pace": 0., "example_density": 1., "explanation_order": 1.}.items()
              if context.preferences.get(key, .5) != value}
    if not values:
        return None
    return {"reason": "最近两轮在同一知识点上需要更多支持，要试试慢一点、先看例子吗？",
            "label": "慢一点，先看例子", "values": values}
