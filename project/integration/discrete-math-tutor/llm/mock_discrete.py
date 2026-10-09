"""Deterministic discrete-mathematics fixtures for offline integration tests."""

from __future__ import annotations

import re
from typing import Any


def _last_user(messages: list[dict[str, str]]) -> str:
    return next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")


def _field(content: str, name: str) -> str:
    match = re.search(re.escape(name) + r"([^\n]*)", content)
    return match.group(1).strip() if match else ""


def mock_reply(messages: list[dict[str, str]], json_mode: bool) -> Any:
    system = next((m.get("content", "") for m in messages if m.get("role") == "system"), "")
    tag_match = re.search(r"\[AGENT:(\w+)\]", system)
    tag = tag_match.group(1) if tag_match else ""
    content = _last_user(messages)
    student = _field(content, "学生最新输入：") or _field(content, "学生最新发言：") or content
    stuck = any(x in student for x in ("不知道", "不懂", "不会", "没思路"))

    if not json_mode:
        if tag == "social_reply":
            return "好的，需要时再回来学离散数学。"
        if stuck:
            return "没关系，先退一步。图可以先看成顶点和连接顶点的边。你能指出图中的一个顶点吗？[1]"
        return "先从一个小概念开始：图由顶点和边组成。你想先看顶点，还是边？[1]"

    if tag == "conversation_router":
        switch = re.search(r"(?:换到|改学|想学|学习)(集合|图论|图|关系|函数|逻辑代数)", student)
        if switch:
            return {"student_move": "statement", "move_status": "", "intent": "switch_topic",
                    "topic": switch.group(1), "confidence": 0.9, "reason": "明确指定新知识点"}
        if student.strip() in ("换个话题", "换一个知识点"):
            return {"student_move": "statement", "move_status": "", "intent": "clarify_task",
                    "topic": "", "confidence": 0.9, "reason": "未指定新知识点"}
        return {"student_move": "statement" if stuck else "question", "move_status": "",
                "intent": "continue", "topic": "", "confidence": 0.8, "reason": "继续当前知识点"}
    if tag == "evidence_extractor":
        return {"evidence": [{"evidence_type": "behavior", "content": student, "confidence": 0.9}] if stuck else [],
                "observation": {"confidence": 0.2, "emotion": "confused", "current_concept": "图"} if stuck else {"current_concept": "图"},
                "hypotheses": []}
    if tag == "lesson_planner":
        return {"goal": "学习图的基本概念", "knowledge_gap": "需确认顶点与边的基本概念",
                "target_mastery": 0.8, "steps": [
                    {"step_id": "S1", "objective": "能指出图中的顶点和边", "completion_criteria": "独立指出顶点和边",
                     "target_mastery": 0.7, "teaching_form": "explain", "suggested_strategy": "worked_example"},
                    {"step_id": "S2", "objective": "能区分有向边和无向边", "completion_criteria": "独立区分两类边",
                     "target_mastery": 0.8, "teaching_form": "quiz", "suggested_strategy": "retrieval_practice"},
                    {"step_id": "S3", "objective": "能写出简单图的顶点集与边集", "completion_criteria": "独立写出 V 和 E",
                     "target_mastery": 0.8, "teaching_form": "quiz", "suggested_strategy": "transfer"}]}
    if tag == "teaching_planner":
        return {"goal": "掌握当前基础概念", "strategy": "worked_example" if stuck else "socratic_questioning",
                "action": "explain" if stuck else "ask_question", "difficulty": "easy", "hint_level": 1,
                "expected_student_behavior": "能说出顶点和边", "rationale": "按基础状态推进"}
    if tag == "strategy_router":
        return {"instructional_move": "worked_example" if stuck else "direct_explanation",
                "action": "give_example" if stuck else "explain", "difficulty": "easy", "hint_level": 1,
                "rationale": "先给简单例子"}
    if tag == "question_designer":
        return {"question_type": "open_explanation", "target_misconception": None,
                "discrimination_goal": "识别顶点和边", "stem": "图中的顶点和边分别是什么？",
                "options": [], "acceptable_free_answer": "顶点是点，边连接顶点"}
    if tag == "quality_checker":
        return {"passed": True, "issues": [], "suggestions": ""}
    if tag == "state_updater":
        return {"confidence": 0.2 if stuck else 0.5, "emotion": "confused" if stuck else "neutral",
                "turn_summary": "学生表示卡住" if stuck else "继续学习图的基本概念",
                "step_completed": False, "step_reason": "尚无独立正确作答",
                "evidence": [], "hypotheses": [], "resolve_misconceptions": False,
                "tutor_error": {"detected": False}}
    if tag == "misconception_resolver":
        return {"matched_id": None, "reason": "无误解"}
    return {}
