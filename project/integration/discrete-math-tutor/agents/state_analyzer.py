"""State Analyzer —— 把证据与观测整合进 StudentState（不再直接调用 LLM）。

【参考实现】OATutor evidence-based mastery；ScaffoldLM 的 learner cognitive state。
【自主衔接】LLM 调用已由 EvidenceExtractor 完成；本模块负责：
- 用指数平滑把观测融合进状态（新观测不覆盖历史估计）；
- 保留证据溯源（证据本身由 MemoryManager 落库）。
"""

from __future__ import annotations

from typing import Optional

from agents.evidence_extractor import AnalysisResult
from llm.client import LLMClient
from models.student_state import StudentState

TEXT_FIELDS = ("current_concept", "emotion", "interaction_preference")


class StateAnalyzer:
    def __init__(self, llm: Optional[LLMClient] = None) -> None:  # llm 保留兼容，不再使用
        self.llm = llm

    def build(self, state: StudentState, analysis: AnalysisResult) -> StudentState:
        new_state = state.model_copy(deep=True)
        alpha = 0.6 if state.turn_count == 0 else 0.4
        new_state.blend_numeric(analysis.observation, alpha=alpha)
        for field in TEXT_FIELDS:
            value = analysis.observation.get(field)
            if value:
                setattr(new_state, field, value)
        return new_state
