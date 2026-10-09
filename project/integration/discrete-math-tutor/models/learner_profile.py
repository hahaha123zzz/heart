"""LearnerProfile —— 学生的长期画像（跨会话持久化）。

【参考实现】GenMentor / LearningMAP 的 learner profile 与个性化记忆。
【自主衔接】teaching_effectiveness：按策略累计"是否带来进展"（EMA），
让 Teaching Policy 不只是"学生喜欢什么"，而是"什么对这个学生真正有效"。
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from pydantic import BaseModel


class LearnerProfile(BaseModel):
    student_id: str = ""
    preferences: Dict[str, float] = {}  # 交互偏好强度 {"step_by_step": 0.88}
    learning_behavior: Dict[str, float] = {}  # 行为统计 {"hint_requests": 3.0}
    teaching_effectiveness: Dict[str, float] = {}  # 策略 -> 有效性(0~1)

    def update_effectiveness(
        self, strategy: str, success: bool, alpha: float = 0.3
    ) -> None:
        if not strategy:
            return
        old = self.teaching_effectiveness.get(strategy, 0.5)
        target = 1.0 if success else 0.0
        self.teaching_effectiveness[strategy] = round(
            alpha * target + (1 - alpha) * old, 3
        )

    def best_strategies(self, top_k: int = 3) -> List[Tuple[str, float]]:
        return sorted(
            self.teaching_effectiveness.items(), key=lambda kv: kv[1], reverse=True
        )[:top_k]
