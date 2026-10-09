"""Teaching Planner —— 输出结构化教学计划（不做自然语言生成）。

【参考实现】ScaffoldLM 的 planning-guided tutoring：先规划，再按步骤驱动多轮对话
（data_synthesis/planning 的 generate_plan.py 与 prompts/planning）。
【自主衔接】输入 = StudentState + learning_goal + 当前课程步骤 + TeachingPolicy 约束；
输出 = 结构化 TeachingPlan JSON；代码校验 LLM 输出（策略必须来自允许列表），
校验失败时回退到 Policy 推荐值，保证"外部策略约束 LLM"。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel

from agents.teaching_policy import select_policy
from llm.client import LLMClient
from models.lesson_plan import LessonStep
from models.student_state import StudentState

ALLOWED_STRATEGIES = [
    "socratic_questioning",
    "scaffolding",
    "worked_example",
    "self_explanation",
    "retrieval_practice",
    "conceptual_comparison",
    "error_based_learning",
    "progressive_hinting",
]
ALLOWED_ACTIONS = ["ask_question", "give_hint", "explain", "give_example", "summarize"]
ALLOWED_DIFFICULTY = ["easy", "medium", "hard"]


class TeachingPlan(BaseModel):
    goal: str
    strategy: str
    action: str
    difficulty: str
    hint_level: int = 1
    expected_student_behavior: str = ""
    rationale: str = ""


SYSTEM_PROMPT = """[AGENT:teaching_planner]
你是 AI Tutor 的"教学规划器"。你不和学生直接对话，只输出结构化的教学计划 JSON。
要求：
1. 本轮教学子目标必须服务于总体学习目标；
2. 如果给了"当前课程步骤"，本轮计划必须对准该步骤的 objective 与 completion_criteria；
3. strategy 只能从给定的允许列表中选择；
4. 结合学生状态选择下一步动作，学生薄弱时步子要小，学生已掌握时允许小结/推进；
5. 如果课程已全部完成：action 用 summarize，做整体总结与迁移应用；
6. 只输出 JSON，不要输出其他文字。格式：
{
  "goal": "本轮教学子目标",
  "strategy": "允许列表中的策略",
  "action": "ask_question|give_hint|explain|give_example|summarize",
  "difficulty": "easy|medium|hard",
  "hint_level": 1到3的整数,
  "expected_student_behavior": "期望学生表现出的行为或回答",
  "rationale": "一句话说明为什么这样教"
}"""


class TeachingPlanner:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def plan(
        self,
        state: StudentState,
        learning_goal: str,
        current_step: Optional[LessonStep] = None,
        curriculum_done: bool = False,
        profile=None,
    ) -> TeachingPlan:
        policy = select_policy(state, current_step, profile)
        step_text = (
            str(current_step.model_dump()) if current_step else "无"
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "总体学习目标：" + learning_goal + "\n"
                    "当前课程步骤：" + step_text + "\n"
                    "课程状态：" + ("已完成全部步骤，本轮做总结与迁移" if curriculum_done else "进行中") + "\n"
                    "学生状态：" + str(state.model_dump()) + "\n"
                    "教学策略约束（来自 Teaching Policy，必须遵守）：" + str(policy) + "\n"
                    "允许的 strategy 列表：" + str(ALLOWED_STRATEGIES)
                ),
            },
        ]
        data = self.llm.chat_json(messages)
        return self._validate(data, policy)

    @staticmethod
    def _validate(data: Dict[str, Any], policy: Dict) -> TeachingPlan:
        strategy = data.get("strategy")
        if strategy not in ALLOWED_STRATEGIES:
            strategy = policy["recommended_strategies"][0]

        action = data.get("action")
        if action not in ALLOWED_ACTIONS:
            action = policy["action"]

        difficulty = data.get("difficulty")
        if difficulty not in ALLOWED_DIFFICULTY:
            difficulty = policy["difficulty"]

        try:
            hint_level = max(1, min(3, int(data.get("hint_level", policy["hint_level"]))))
        except (TypeError, ValueError):
            hint_level = policy["hint_level"]

        return TeachingPlan(
            goal=data.get("goal") or "推进学习目标",
            strategy=strategy,
            action=action,
            difficulty=difficulty,
            hint_level=hint_level,
            expected_student_behavior=data.get("expected_student_behavior", ""),
            rationale=data.get("rationale", ""),
        )
