"""Lesson Planner —— 课程级多步教学计划（先有计划，再开始对话）。

【参考实现】
- GenMentor（WWW 2025）：学习目标 → 分析背景 → 找知识差距 → 规划学习路径；
- OATutor：Learning Objectives + Target Mastery + skill 拆分（S1/S2/…）；
- ScaffoldLM：step-aligned pedagogical plan。

【自主衔接】计划存入 Memory；Orchestrator 按 steps_mastery 选择当前步骤；
State Updater 评估步骤达成后推进；全部步骤完成后明确结课。
"""

from __future__ import annotations

from typing import Any, Dict, List

from llm.client import LLMClient
from models.lesson_plan import TEACHING_FORMS, LessonPlan, LessonStep
from models.student_state import StudentState

SYSTEM_PROMPT = """[AGENT:lesson_planner]
你是 AI Tutor 的"课程规划器"。给定学习目标和学生当前状态，按流程规划教学：
1. 先分析学生背景与已有掌握，找出知识差距（写进 knowledge_gap）；
2. 把教学拆成 3 到 5 个步骤（不超过 5 步）；
3. 每一步 objective 必须是可观察的行为（"能说出…""能区分…""能应用…"），
   禁止"了解/理解"这类无法观察的词；
4. 每一步给出 completion_criteria（怎样算过关）与 target_mastery（0 到 1 的数字）；
5. 步骤顺序：先诊断基础 → 建立概念 → 简单检查 → 迁移应用；
6. 兼顾效率：不要把简单目标拆成大量重复练习。
7. 本项目是离散数学助教；目标和步骤必须有教材摘录支持，不编造定理或公式。
只输出 JSON：
{
  "goal": "学习目标",
  "knowledge_gap": "一句话说明学生当前最大的知识差距",
  "target_mastery": 0.8,
  "steps": [
    {"step_id": "S1", "objective": "...", "completion_criteria": "...",
     "target_mastery": 0.8, "teaching_form": "explain|socratic|quiz",
     "suggested_strategy": "策略名"}
  ]
}"""


class LessonPlanner:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def create(self, goal: str, state: StudentState, textbook_excerpts: str = "") -> LessonPlan:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "学习目标：" + goal + "\n"
                    "学生当前状态：" + str(state.model_dump()) + "\n"
                    "离散数学教材摘录：" + textbook_excerpts
                ),
            },
        ]
        data = self.llm.chat_json(messages)
        return self._validate(data, goal)

    @staticmethod
    def _validate(data: Dict[str, Any], goal: str) -> LessonPlan:
        raw_steps = data.get("steps") or []
        steps: List[LessonStep] = []
        for index, item in enumerate(raw_steps[:5], start=1):
            if not isinstance(item, dict) or not item.get("objective"):
                continue
            form = item.get("teaching_form")
            if form not in TEACHING_FORMS:
                form = "socratic"
            try:
                target = float(item.get("target_mastery", 0.8))
            except (TypeError, ValueError):
                target = 0.8
            steps.append(
                LessonStep(
                    step_id=str(item.get("step_id") or "S" + str(index)),
                    objective=str(item["objective"]),
                    completion_criteria=str(
                        item.get("completion_criteria") or "学生能正确回答相关问题"
                    ),
                    target_mastery=max(0.0, min(1.0, target)),
                    teaching_form=form,
                    suggested_strategy=str(
                        item.get("suggested_strategy") or "socratic_questioning"
                    ),
                )
            )
        if not steps:
            steps = [
                LessonStep(
                    step_id="S1",
                    objective=goal or "掌握核心内容",
                    completion_criteria="学生能用自己的话复述核心内容",
                )
            ]
        try:
            plan_target = float(data.get("target_mastery", 0.8))
        except (TypeError, ValueError):
            plan_target = 0.8
        return LessonPlan(
            goal=goal,
            target_mastery=max(0.0, min(1.0, plan_target)),
            steps=steps,
            current_step=steps[0].step_id,
            status="in_progress",
        )
