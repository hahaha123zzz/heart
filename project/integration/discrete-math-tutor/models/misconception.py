"""Misconception —— 迷思概念及其生命周期状态机。

【参考实现】ScaffoldLM 的认知状态推断；本项目的关键扩展：误解不再是永久字符串。
【自主衔接】状态迁移由**本地规则**（证据数量 + 置信度阈值）判定，
LLM 只负责提供"候选假设 + 支持证据"，所以错误诊断可以被后续证据推翻（dismissed），
学生真正掌握后标记 resolved。
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

MISCONCEPTION_STATUSES = [
    "hypothesis",  # 假设
    "supported",  # 有支持证据
    "confirmed",  # 较多证据确认
    "dismissed",  # 被反证推翻
    "resolved",  # 学生已纠正
]

# 规范误解类型（去重基准）：LLM 应优先从这里选择 type
CANONICAL_TYPES = {
    "vertex_edge_confusion": "混淆图的顶点与边",
    "directed_undirected_confusion": "混淆有向边与无向边",
    "path_cycle_confusion": "混淆路径、闭路径与回路",
    "set_element_confusion": "混淆集合与元素",
    "relation_function_confusion": "把一般关系误当成函数",
    "implication_converse_confusion": "混淆蕴含与其逆命题",
}

# 常见同义/中外文别名 -> 规范类型
_TYPE_ALIASES = {
    "顶点和边混淆": "vertex_edge_confusion",
    "有向无向混淆": "directed_undirected_confusion",
    "路径回路混淆": "path_cycle_confusion",
    "集合元素混淆": "set_element_confusion",
    "关系函数混淆": "relation_function_confusion",
}


def normalize_type(raw: str) -> str:
    """把误解 type 规范化，尽量收敛到同一个 key，便于精确匹配去重。"""
    if not raw:
        return ""
    key = raw.strip().lower().replace(" ", "_").replace("-", "_")
    return _TYPE_ALIASES.get(key, key)


class Misconception(BaseModel):
    id: Optional[int] = None
    knowledge_point: str = ""
    type: str = ""  # 短标签，如 emotion_suppression
    description: str = ""
    confidence: float = 0.0
    evidence_count: int = 0
    status: str = "hypothesis"

    def add_supporting_evidence(self, confidence: float) -> "Misconception":
        """记一条支持证据，并按阈值推进状态。"""
        self.evidence_count += 1
        if self.evidence_count == 1:
            self.confidence = float(confidence)
        else:
            self.confidence = round(0.6 * self.confidence + 0.4 * float(confidence), 3)
        self._apply_thresholds()
        return self

    def _apply_thresholds(self) -> None:
        if self.status in ("dismissed", "resolved"):
            return
        if self.confidence >= 0.8 or self.evidence_count >= 3:
            self.status = "confirmed"
        elif self.confidence >= 0.6 or self.evidence_count >= 2:
            self.status = "supported"
        else:
            self.status = "hypothesis"

    def dismiss(self) -> "Misconception":
        self.status = "dismissed"
        return self

    def resolve(self) -> "Misconception":
        self.status = "resolved"
        return self
