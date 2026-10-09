"""Strategy Router —— 决定"这一轮用什么教学动作"（讲解 / 提问 / 提示 / 反例 / …）。

【参考实现】
- Learning to Prompt（arXiv:2606.20138）：按学生情况动态选教学策略（prompt/strategy router）；
- TACT（arXiv:2608.03952）：Tutor-Strategy Taxonomy（13 种）+ Student-Move Taxonomy；
- Tutor Move Taxonomy（arXiv:2603.05778）："引出学生推理" vs "直接给答案"的参与度光谱。

【自主衔接】两级决策，保持"外部策略约束 LLM"：
1. 规则预筛：按 student_move + 学生状态 + 画像有效性，从策略库筛出 2~3 个候选；
2. LLM 只能在候选中选（代码校验，越界回退规则首选）。
另留 strategy_temperature（Learning to Prompt 发现随机采样策略有时更好）。
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from agents.teaching_policy import load_library
from llm.client import LLMClient
from models.lesson_plan import LessonStep
from models.student_state import StudentState

MOVE_ACTION_DEFAULTS = {
    "direct_explanation": "explain",
    "socratic_questioning": "ask_question",
    "hint": "give_hint",
    "scaffolding": "give_hint",
    "worked_example": "give_example",
    "conceptual_comparison": "ask_question",
    "counterexample": "give_example",
    "self_explanation": "ask_question",
    "retrieval_practice": "ask_question",
    "guided_revision": "give_hint",
    "direct_correction": "explain",
    "transfer": "ask_question",
    "summary": "summarize",
}
ALLOWED_ACTIONS = ["ask_question", "give_hint", "explain", "give_example", "summarize"]
ALLOWED_DIFFICULTY = ["easy", "medium", "hard"]
NUM_CANDIDATES = 3


class InstructionalMove(BaseModel):
    instructional_move: str = "socratic_questioning"
    action: str = "ask_question"
    difficulty: str = "medium"
    hint_level: int = 1
    rationale: str = ""


SYSTEM_PROMPT = """[AGENT:strategy_router]
你是 AI Tutor 的"教学策略路由器"。根据学生这一轮的 move、学生状态、当前步骤，
从给定的**候选教学动作**中选出最合适的一个（只能从候选里选）。
判断原则：
1. 学生缺基础 -> 直接讲解/样例；学生有基础 -> 提问/自我解释；
2. 学生答错且错误明确 -> 直接纠正；存在误解 -> 反例/概念对比；只是部分对 -> 引导修正；
3. 学生答对 -> 自我解释/迁移/总结，不要重复提问；
4. 连续两轮用同一动作不好，尽量变化；
5. 情绪低落时降低挑战、多给支持。
只输出 JSON：
{
  "instructional_move": "候选 id 之一",
  "action": "ask_question|give_hint|explain|give_example|summarize",
  "difficulty": "easy|medium|hard",
  "hint_level": 1到3的整数,
  "rationale": "一句话理由"
}"""


def _move_key(student_move: str, move_status: str) -> str:
    if student_move == "attempt" and move_status:
        return "attempt_" + move_status
    return student_move


class StrategyRouter:
    def __init__(self, llm: LLMClient, temperature: float = 0.0) -> None:
        self.llm = llm
        self.library = load_library()
        self.temperature = temperature  # >0 时在候选中随机采样

    # ---- 规则预筛：从策略库筛出 2~3 个候选 -------------------------
    def _prefilter(
        self,
        move_key: str,
        state: StudentState,
        current_step: Optional[LessonStep],
        profile,
        recent_moves: Optional[List[str]],
    ) -> List[Dict[str, Any]]:
        gap = state.calibration_gap
        scored = []
        for item in self.library:
            score = 0.0
            if move_key in item.get("fits_moves", []):
                score += 2.0
            if state.has_misconception:
                if item["id"] in ("counterexample", "conceptual_comparison"):
                    score += 1.5
                if item["id"] == "direct_correction":
                    score += 0.5
            if state.mastery < 0.35:
                if item["id"] in ("worked_example", "direct_explanation", "scaffolding"):
                    score += 1.5
                if item["id"] == "socratic_questioning":
                    score -= 0.5
            if state.emotion in ("confused", "frustrated"):
                if item["id"] in ("scaffolding", "hint"):
                    score += 1.2
                if item["id"] == "direct_explanation":
                    score += 0.5
            if gap > 0.25:
                if item["id"] in ("retrieval_practice", "socratic_questioning"):
                    score += 1.2
            if gap < -0.25:
                if item["id"] in ("scaffolding", "hint"):
                    score += 1.0
            if state.mastery >= 0.7 and not state.has_misconception:
                if item["id"] in ("transfer", "retrieval_practice", "summary"):
                    score += 1.2
            if state.metacognition < 0.4 and item["id"] == "self_explanation":
                score += 1.2
            if current_step is not None:
                if current_step.teaching_form == "quiz" and item["id"] == "retrieval_practice":
                    score += 1.0
                if current_step.teaching_form == "explain" and item["id"] == "direct_explanation":
                    score += 1.0
            if profile is not None:
                eff = profile.teaching_effectiveness.get(item["id"])
                if eff is not None:
                    score += (eff - 0.5) * 1.5
            if recent_moves and item["id"] in recent_moves[-2:]:
                score -= 1.0
            scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        top = [item for _, item in scored[:NUM_CANDIDATES]]
        return top or [self.library[0]]

    # ---- LLM 在候选中选 -------------------------------------------
    def select(
        self,
        student_move: str,
        move_status: str,
        state: StudentState,
        current_step: Optional[LessonStep],
        profile=None,
        recent_moves: Optional[List[str]] = None,
        student_input: str = "",
    ) -> InstructionalMove:
        candidates = self._prefilter(
            _move_key(student_move, move_status), state, current_step, profile, recent_moves
        )
        if self.temperature > 0 and len(candidates) > 1:
            weights = [1.0] * len(candidates)
            candidates = random.choices(candidates, weights=weights, k=1) + [
                c for c in candidates if c is not candidates[0]
            ][: NUM_CANDIDATES - 1]
        payload = [
            {"id": c["id"], "name_cn": c["name_cn"], "when_to_use": c["when_to_use"]}
            for c in candidates
        ]
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "候选教学动作：" + str(payload) + "\n"
                    "学生 move：" + _move_key(student_move, move_status) + "\n"
                    "学生状态：" + str(state.model_dump()) + "\n"
                    "当前步骤：" + (str(current_step.model_dump()) if current_step else "无") + "\n"
                    "最近用过的动作：" + str(recent_moves or []) + "\n"
                    "学生最新发言：" + student_input
                ),
            },
        ]
        data = self.llm.chat_json(messages)
        return self._validate(data, candidates)

    @staticmethod
    def _validate(data: Dict[str, Any], candidates: List[Dict[str, Any]]) -> InstructionalMove:
        ids = [c["id"] for c in candidates]
        chosen = data.get("instructional_move")
        if chosen not in ids:
            chosen = ids[0]
        action = data.get("action")
        if action not in ALLOWED_ACTIONS:
            action = MOVE_ACTION_DEFAULTS.get(chosen, "ask_question")
        difficulty = data.get("difficulty")
        if difficulty not in ALLOWED_DIFFICULTY:
            difficulty = "medium"
        try:
            hint_level = max(1, min(3, int(data.get("hint_level", 1))))
        except (TypeError, ValueError):
            hint_level = 1
        return InstructionalMove(
            instructional_move=chosen,
            action=action,
            difficulty=difficulty,
            hint_level=hint_level,
            rationale=str(data.get("rationale") or ""),
        )
