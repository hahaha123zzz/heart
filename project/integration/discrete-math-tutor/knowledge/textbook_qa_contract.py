"""Product contract for textbook-only question answering."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


ALLOWED_INTENTS = frozenset({
    "definition",
    "concept",
    "theorem_explanation",
    "property",
    "formula_meaning",
    "comparison",
    "textbook_example",
})

SOLVING_ACTIONS = (
    "做题", "练习题", "出一道", "出一道题", "新题", "解答题",
    "计算一下", "求值", "求结果", "解方程", "解不等式",
    "证明以下", "证明下列", "求证", "推导一下", "推导出",
    "设计一个算法", "设计一个新算法", "编写程序", "生成一个新例子",
)

TEXTBOOK_ANCHORS = (
    "教材", "书中", "原文", "这一节", "本节", "本章", "这个定理",
    "这条定理", "这个公式", "书里的例子", "教材中的例子",
)

ANSWER_SECTIONS = (
    "直接回答",
    "教材依据和关键条件",
    "简短解释",
    "教材引用",
)

REFUSAL_MESSAGE = (
    "当前系统只回答教材中已有的定义、概念、定理、性质、公式含义、"
    "区别和教材解释，不做题、不计算新题、不证明新题，也不使用教材外知识。"
)

CLARIFY_MESSAGE = (
    "请补充你想查询的教材概念、定理或公式名称。"
    "如果是在追问上一轮内容，请同时说明具体指哪个对象。"
)


@dataclass(frozen=True)
class QAContractDecision:
    allowed: bool
    intent: str
    needs_clarification: bool
    reason: str
    reply: str = ""


def _compact(value: str) -> str:
    return re.sub(
        r"[\s“”「」\"'，。！？；：,.!?;:()（）【】\[\]]+",
        "",
        unicodedata.normalize("NFKC", value or ""),
    )


def classify_question(question: str, *, has_context: bool = False) -> QAContractDecision:
    """Classify whether the request belongs to textbook question answering."""

    text = _compact(question)
    if len(text) < 2:
        return QAContractDecision(
            False,
            "ambiguous",
            True,
            "问题没有足够对象",
            CLARIFY_MESSAGE,
        )

    has_solving_action = any(term in text for term in SOLVING_ACTIONS)
    has_textbook_anchor = any(term in text for term in TEXTBOOK_ANCHORS)
    asks_existing_proof = (
        ("证明" in text or "推导" in text)
        and has_textbook_anchor
        and not any(term in text for term in ("证明以下", "证明下列", "求证", "推导出"))
    )
    if has_solving_action and not asks_existing_proof:
        return QAContractDecision(
            False,
            "exercise_or_new_derivation",
            False,
            "用户要求做题、计算、证明新题或生成新内容",
            REFUSAL_MESSAGE,
        )

    ambiguous_reference = any(
        term in text for term in ("这个", "那个", "这样", "那样", "它", "上题", "刚才")
    )
    if ambiguous_reference and not has_context and len(text) <= 10:
        return QAContractDecision(
            False,
            "ambiguous",
            True,
            "代词没有可绑定对象",
            CLARIFY_MESSAGE,
        )

    if any(term in text for term in ("定义", "什么是", "是什么", "含义", "概念")):
        intent = "definition"
    elif any(term in text for term in ("区别", "不同", "比较", "异同")):
        intent = "comparison"
    elif "定理" in text:
        intent = "theorem_explanation"
    elif any(term in text for term in ("公式", "表达式", "符号")):
        intent = "formula_meaning"
    elif any(term in text for term in ("性质", "特点", "条件")):
        intent = "property"
    elif any(term in text for term in ("教材中的例子", "书里的例子", "这个例子")):
        intent = "textbook_example"
    elif any(term in text for term in ("为什么", "怎么解释", "如何理解", "说明什么")):
        intent = "concept"
    else:
        return QAContractDecision(
            False,
            "not_textbook_lookup",
            False,
            "没有识别为教材概念、定理、公式或比较问题",
            REFUSAL_MESSAGE,
        )
    return QAContractDecision(True, intent, False, "教材内容查询")


def answer_shape() -> tuple[str, ...]:
    """Return the required answer sections in display order."""
    return ANSWER_SECTIONS
