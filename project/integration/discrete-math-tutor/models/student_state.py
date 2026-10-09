"""学生状态模型 —— 系统的核心数据结构（状态驱动教学的基础）。

字段来源（详见 README 借鉴表）：
- current_concept / mastery / misconception ->
  Learner Modeling & Knowledge Tracing（ScaffoldLM learner state、pyKT 等）
- confidence -> Self-efficacy（Bandura）：与 mastery 的差值 calibration_gap
  用于检测"过度自信 / 信心不足"
- metacognition -> Metacognition（Flavell）
- emotion -> Affect / 学业情绪研究（仅作交互状态，不做心理诊断）
- steps_mastery -> OATutor：步骤级技能掌握度（S1/S2/…，达到 target 才算学会）
- misconceptions -> Misconception Modeling（列表 + 状态，替代单一字符串）
- mistake_patterns -> Adaptive AI Tutor 的 MistakePattern：错误模式独立建模、跨轮累计
- evidence -> OATutor "evidence-based mastery"：掌握度只认独立有效证据
- interaction_preference / cognitive_load -> 工程组合 / Cognitive Load Theory（预留）

【自主衔接】统一数据结构 + blend_numeric() 融合方法
（借鉴 KT：新观测不覆盖旧估计，而是加权融合）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from models.misconception import Misconception

EMOTIONS = ["confused", "frustrated", "engaged", "bored", "neutral"]
INTERACTION_PREFERENCES = ["step_by_step", "example_first", "challenge"]


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


class MistakePattern(BaseModel):
    pattern: str = ""  # 反复出现的错误模式
    count: int = 1
    last_seen: str = ""


class StudentState(BaseModel):
    student_id: str = "default"
    current_concept: str = ""
    mastery: float = Field(0.5, ge=0.0, le=1.0, description="当前概念整体掌握度")
    confidence: float = Field(0.5, ge=0.0, le=1.0, description="自我效能感 / 自评信心")
    metacognition: float = Field(0.5, ge=0.0, le=1.0, description="元认知水平")
    misconception: Optional[str] = None  # 主要误解摘要（兼容旧字段）
    emotion: str = "neutral"
    interaction_preference: str = "step_by_step"
    cognitive_load: Optional[str] = None  # 预留：low / medium / high
    turn_count: int = 0
    last_summary: str = ""

    # ---- 富化字段（OATutor / Adaptive AI Tutor / Misconception Modeling）----
    steps_mastery: Dict[str, float] = {}  # {"S1": 0.8, "S2": 0.4, ...}
    misconceptions: List[Misconception] = []
    mistake_patterns: List[MistakePattern] = []
    evidence: List[str] = []  # 步骤级学习证据
    remaining_gap: str = ""  # 当前最欠缺的能力

    @property
    def calibration_gap(self) -> float:
        """自我评估偏差：>0 过度自信，<0 信心不足。"""
        return round(self.confidence - self.mastery, 3)

    @property
    def has_misconception(self) -> bool:
        """是否存在尚未解决的误解（排除 dismissed / resolved）。"""
        return bool(self.misconception) or any(
            m.status in ("hypothesis", "supported", "confirmed")
            for m in self.misconceptions
        )

    def blend_numeric(
        self,
        updates: Dict[str, Any],
        alpha: float = 0.4,
        fields: tuple = ("mastery", "confidence", "metacognition"),
    ) -> "StudentState":
        """用新观测更新数值字段（含步骤级掌握度）。

        借鉴 Knowledge Tracing：单轮观测不直接覆盖历史估计，而是指数平滑。
        """
        for field in fields:
            value = updates.get(field)
            if value is None:
                continue
            old = float(getattr(self, field))
            setattr(self, field, _clamp(alpha * float(value) + (1.0 - alpha) * old))
        step_updates = updates.get("steps_mastery")
        if isinstance(step_updates, dict):
            for key, value in step_updates.items():
                if value is None:
                    continue
                old = float(self.steps_mastery.get(key, 0.5))
                self.steps_mastery[key] = _clamp(
                    alpha * float(value) + (1.0 - alpha) * old
                )
        return self
