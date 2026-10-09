"""Evidence Extractor —— 从学生输入提取结构化学习证据（+ 状态观测 + 误解假设）。

【参考实现】ScaffoldLM 的 assessment/evidence；OATutor "只认独立有效证据"。
【自主衔接】按既定决策，本模块与 State Analyzer **共用一次 LLM 调用**（模块独立、调用合并）：
本模块发起调用并返回 AnalysisResult（证据 / 观测 / 误解假设），
State Analyzer 只负责把观测整合进 StudentState。
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel

from llm.client import LLMClient
from models.evidence import Evidence
from models.misconception import CANONICAL_TYPES
from models.student_state import StudentState


class MisconceptionHypothesis(BaseModel):
    type: str = ""
    description: str = ""
    confidence: float = 0.5


class AnalysisResult(BaseModel):
    evidence: List[Evidence] = []
    observation: Dict[str, Any] = {}
    hypotheses: List[MisconceptionHypothesis] = []


SYSTEM_PROMPT = """[AGENT:evidence_extractor]
你是 AI Tutor 的"证据提取器"。从学生这句话中提取**可验证的学习证据**，
并给出学生状态的观测值。不要直接下最终结论，只给证据与估计。
只输出 JSON：
{
  "evidence": [
    {"evidence_type": "conceptual_understanding|misconception|partial|affect|behavior",
     "content": "证据原文或描述", "confidence": 0.0到1.0}
  ],
  "observation": {
    "mastery": 0.0到1.0, "confidence": 0.0到1.0, "metacognition": 0.0到1.0,
    "emotion": "confused|frustrated|engaged|bored|neutral",
    "current_concept": "当前概念",
    "interaction_preference": "step_by_step|example_first|challenge"
  },
  "hypotheses": [
    {"type": "短标签", "description": "候选误解", "confidence": 0.0到1.0}
  ]
}
要求：
1. evidence 必须基于学生真实说的话（有原文依据），不要凭印象编造；
2. hypotheses 只在学生表现出错误理解时给出；
3. 单句话不能作为最终结论，只作为一条证据。"""


class EvidenceExtractor:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def analyze(
        self,
        student_input: str,
        state: StudentState,
        history: List[Dict[str, str]],
    ) -> AnalysisResult:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "学生当前状态：" + str(state.model_dump()) + "\n"
                    "最近对话：" + str(history[-6:]) + "\n"
                    "可选规范误解类型（hypotheses 的 type 优先从这里选）："
                    + "、".join(sorted(CANONICAL_TYPES))
                    + "\n学生最新输入：" + student_input
                ),
            },
        ]
        data = self.llm.chat_json(messages)
        return self._validate(data)

    @staticmethod
    def _validate(data: Dict[str, Any]) -> AnalysisResult:
        evidence: List[Evidence] = []
        for item in data.get("evidence") or []:
            if not isinstance(item, dict) or not item.get("content"):
                continue
            try:
                confidence = float(item.get("confidence", 0.5))
            except (TypeError, ValueError):
                confidence = 0.5
            evidence.append(
                Evidence(
                    evidence_type=str(item.get("evidence_type") or "conceptual_understanding"),
                    content=str(item["content"]),
                    confidence=max(0.0, min(1.0, confidence)),
                )
            )
        hypotheses: List[MisconceptionHypothesis] = []
        for item in data.get("hypotheses") or []:
            if not isinstance(item, dict) or not item.get("description"):
                continue
            try:
                confidence = float(item.get("confidence", 0.5))
            except (TypeError, ValueError):
                confidence = 0.5
            hypotheses.append(
                MisconceptionHypothesis(
                    type=str(item.get("type") or ""),
                    description=str(item["description"]),
                    confidence=max(0.0, min(1.0, confidence)),
                )
            )
        observation = data.get("observation")
        if not isinstance(observation, dict):
            observation = {}
        return AnalysisResult(
            evidence=evidence, observation=observation, hypotheses=hypotheses
        )
