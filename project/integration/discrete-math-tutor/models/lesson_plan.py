"""课程级教学计划 —— 解决"教到什么时候算完"。

【参考实现】
- OATutor（CMU，Bayesian Knowledge Tracing + 自适应教学）：skill 拆分、
  Learning Objectives、Target Mastery、按掌握度决定推进/跳过；
- GenMentor（WWW 2025，GeminiLight/gen-mentor）：目标 → 知识差距 → 规划学习路径；
- ScaffoldLM：step-level pedagogical plan、步骤达成评估、明确结课。

【自主衔接】步骤选择（first_unmastered）、推进与结课逻辑由 Orchestrator 驱动。
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

TEACHING_FORMS = ["explain", "socratic", "quiz"]


class LessonStep(BaseModel):
    step_id: str = "S1"
    objective: str = ""  # 可观察的行为目标，如"能说出两个概念的区别"
    completion_criteria: str = ""  # 怎样算这一步过关
    target_mastery: float = Field(0.8, ge=0.0, le=1.0)  # OATutor：达到阈值才算学会
    teaching_form: str = "socratic"  # explain / socratic / quiz
    suggested_strategy: str = "socratic_questioning"


class LessonPlan(BaseModel):
    goal: str = ""
    target_mastery: float = Field(0.8, ge=0.0, le=1.0)
    steps: List[LessonStep] = []
    current_step: str = ""
    status: str = "in_progress"  # in_progress / completed

    def get_step(self, step_id: str) -> Optional[LessonStep]:
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None

    def current(self) -> Optional[LessonStep]:
        return self.get_step(self.current_step)

    def first_unmastered(self, steps_mastery: Dict[str, float]) -> Optional[LessonStep]:
        """OATutor 思想：按顺序找第一个未达标的步骤（已掌握的步骤直接跳过）。"""
        for step in self.steps:
            if steps_mastery.get(step.step_id, 0.0) < step.target_mastery:
                return step
        return None

    def advance(self, steps_mastery: Dict[str, float]) -> bool:
        """推进到下一个未达标步骤；全部达标则结课。返回是否已结课。"""
        nxt = self.first_unmastered(steps_mastery)
        if nxt is None:
            self.status = "completed"
            self.current_step = ""
            return True
        self.current_step = nxt.step_id
        return False

    def progress(self) -> Dict:
        total = len(self.steps)
        index = next(
            (i for i, s in enumerate(self.steps, 1) if s.step_id == self.current_step),
            total,
        )
        current = self.current()
        return {
            "goal": self.goal,
            "status": self.status,
            "current_step": self.current_step,
            "current_step_index": index,
            "total_steps": total,
            "current_objective": current.objective if current else "",
        }
