"""Evidence —— 学习证据（Student Model 的可溯源原子事实）。

【参考实现】ScaffoldLM 的 assessment/evidence 思路；OATutor "只认独立有效证据"。
【自主衔接】mastery / 误解判断都必须能追溯到证据，避免"LLM 一句话就下结论"。
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

EVIDENCE_TYPES = [
    "conceptual_understanding",  # 概念理解
    "misconception",  # 暴露迷思概念
    "partial",  # 部分理解
    "affect",  # 情绪表现
    "behavior",  # 学习行为（提问/请求提示等）
    "tutor_error",  # 教学错误（审计用）
]


class Evidence(BaseModel):
    knowledge_point: str = ""
    evidence_type: str = "conceptual_understanding"
    content: str = ""
    confidence: float = Field(0.5, ge=0.0, le=1.0)
    # 若该证据指向某个误解，由 MemoryManager 关联
    misconception_type: Optional[str] = None
    misconception_description: Optional[str] = None
