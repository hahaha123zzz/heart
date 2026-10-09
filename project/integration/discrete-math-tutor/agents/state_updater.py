"""State Updater —— 一轮结束后：证据式评估 + 步骤达成 + 教学错误自检。

【参考实现】
- OATutor：掌握度达到 target mastery 才算学会，只认独立证据；
- ScaffoldLM assessment-driven memory：评估本轮教学目标是否达成；
- Adaptive AI Tutor：错误模式跨轮累计（这里并入 StudentState.mistake_patterns）。

【自主衔接】一次 LLM 调用同时产出：状态观测 + 新证据 + 误解假设 +
步骤达成判断 + 教学错误自检（供 Tutor Error Detector 解析）。
数值指数平滑融合；证据与误解由 Orchestrator 交给 MemoryManager 落库。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from agents.evidence_extractor import MisconceptionHypothesis
from llm.client import LLMClient
from models.evidence import Evidence
from models.lesson_plan import LessonStep
from models.misconception import CANONICAL_TYPES
from models.student_state import EMOTIONS, INTERACTION_PREFERENCES, StudentState

MAX_EVIDENCE = 20


class UpdateResult(BaseModel):
    state: StudentState
    step_completed: bool = False
    step_reason: str = ""
    new_evidence: List[Evidence] = []
    new_hypotheses: List[MisconceptionHypothesis] = []
    resolve_misconceptions: bool = False
    raw: Dict[str, Any] = {}


SYSTEM_PROMPT = """[AGENT:state_updater]
你是 AI Tutor 的学生状态更新器。根据"本轮学生状态 + 当前步骤 + 学生输入 +
Tutor 回复 + 质检结果"，做证据式评估。只输出 JSON：
{
  "mastery": 0.0到1.0, "confidence": 0.0到1.0, "metacognition": 0.0到1.0,
  "emotion": "confused|frustrated|engaged|bored|neutral",
  "misconception": "仍存在的主要误解摘要，无则 null",
  "interaction_preference": "step_by_step|example_first|challenge",
  "remaining_gap": "当前最欠缺的能力（一句话）",
  "turn_summary": "这一轮发生了什么（一句话）",
  "steps_mastery": {"S1": 0.0到1.0},
  "evidence": [{"evidence_type": "conceptual_understanding|misconception|partial|affect|behavior",
                "content": "...", "confidence": 0.0到1.0}],
  "hypotheses": [{"type": "短标签", "description": "候选误解", "confidence": 0.0到1.0}],
  "resolve_misconceptions": true 或 false,
  "step_completed": true 或 false,
  "step_reason": "步骤达成或未达成的依据",
  "tutor_error": {"detected": false, "error_type": "wrong_explanation|misjudged_state|off_plan|bad_question", "reason": "", "rollback": false}
}
原则：
1. 只有学生真正独立展示出能力时才给高掌握度（Tutor 讲过不等于学生会）；
2. step_completed 仅在满足当前步骤 completion_criteria 且掌握度达到 target_mastery 时为 true；
3. 如果本轮 Tutor 的讲解/题目明显有误或误判了学生，把 tutor_error.detected 置 true 并建议 rollback；
4. 学生已能用正确方式解释时，resolve_misconceptions 置 true。"""


class StateUpdater:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def update(
        self,
        state: StudentState,
        student_input: str,
        response: str,
        current_step: Optional[LessonStep] = None,
        quality_issues: Optional[List[str]] = None,
        textbook_excerpts: str = "",
    ) -> UpdateResult:
        step_text = str(current_step.model_dump()) if current_step else "无"
        issues_text = "；".join(quality_issues or []) or "无"
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "本轮开始时的学生状态：" + str(state.model_dump()) + "\n"
                    "当前课程步骤：" + step_text + "\n"
                    "学生输入：" + student_input + "\n"
                    "Tutor 回复：" + response + "\n"
                    "质量检查发现的问题：" + issues_text + "\n"
                    "教材摘录：" + textbook_excerpts + "\n"
                    "可选规范误解类型（hypotheses 的 type 优先从这里选）："
                    + "、".join(sorted(CANONICAL_TYPES))
                ),
            },
        ]
        data = self.llm.chat_json(messages)

        new_state = state.model_copy(deep=True)
        new_state.blend_numeric(data, alpha=0.4)
        if data.get("emotion") in EMOTIONS:
            new_state.emotion = data["emotion"]
        if "misconception" in data:
            new_state.misconception = data["misconception"] or None
        if data.get("interaction_preference") in INTERACTION_PREFERENCES:
            new_state.interaction_preference = data["interaction_preference"]
        if data.get("remaining_gap"):
            new_state.remaining_gap = str(data["remaining_gap"])
        new_state.turn_count += 1
        new_state.last_summary = str(data.get("turn_summary") or new_state.last_summary)

        new_evidence = _parse_evidence(data.get("evidence"))
        new_hypotheses = _parse_hypotheses(data.get("hypotheses"))

        return UpdateResult(
            state=new_state,
            step_completed=bool(data.get("step_completed", False)),
            step_reason=str(data.get("step_reason") or ""),
            new_evidence=new_evidence,
            new_hypotheses=new_hypotheses,
            resolve_misconceptions=bool(data.get("resolve_misconceptions", False)),
            raw=data if isinstance(data, dict) else {},
        )


def _parse_evidence(raw: Any) -> List[Evidence]:
    result: List[Evidence] = []
    for item in raw or []:
        if not isinstance(item, dict) or not item.get("content"):
            continue
        try:
            confidence = float(item.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        result.append(
            Evidence(
                evidence_type=str(item.get("evidence_type") or "conceptual_understanding"),
                content=str(item["content"]),
                confidence=max(0.0, min(1.0, confidence)),
            )
        )
    return result


def _parse_hypotheses(raw: Any) -> List[MisconceptionHypothesis]:
    result: List[MisconceptionHypothesis] = []
    for item in raw or []:
        if not isinstance(item, dict) or not item.get("description"):
            continue
        try:
            confidence = float(item.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        result.append(
            MisconceptionHypothesis(
                type=str(item.get("type") or ""),
                description=str(item["description"]),
                confidence=max(0.0, min(1.0, confidence)),
            )
        )
    return result
