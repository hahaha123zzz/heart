"""Deterministic follow-up directives for multi-turn tutoring.

The router and response generator already receive history, but a short
follow-up such as "没听懂，再简单点" is ambiguous without an explicit target.
These directives name the object the student is referring to and separate a
depth change from an accuracy requirement, so the model cannot silently answer
the trailing check question or turn "不要编造数据" into a hint-only request.
"""

from __future__ import annotations

import re

SIMPLIFY_PATTERN = re.compile(
    r"没听懂|听不懂|没理解|不明白|"
    r"换(?:一)?(?:个|种)(?:说法|解释|讲法|表述)|"
    r"再简单|简单点|简单些|说得简单|讲得简单|简化(?:一下|表达|说明)|"
    r"(?:说得|讲得|说|讲)通俗(?:一点|一些|点|些|易懂)?(?=$|[，。！？；])|"
    r"通俗(?:一点|一些|点|些|易懂)|大白话|"
    r"浅显(?:一点|一些|点|些)|再(?:讲|说|解释)(?:一遍|一下)"
)
COMPARE_FOLLOWUP_PATTERN = re.compile(
    r"继续比较|接着比较|再比较|只.{0,8}(?:确认|比较).{0,16}(?:设计|方法|概念|对象)|"
    r"保留.{0,12}(?:对象|目标)|不要引入其他"
)
NARROW_SCOPE_PATTERN = re.compile(
    # “只确认/只想再确认/只讲某个对象”本身就缩小了范围，不要求再说“不要引入其他”。
    # 但“每类只讲一个要点/只解释一遍”是数量或深度限制，不是单对象范围。
    r"(?:只|仅)(?:想|要|需|是)?(?:再|先)?"
    r"(?:确认|讲|说|解释|回答|问|知道|了解)(?:一下)?"
    r"(?!(?:[一二三四五六七八九十两几])\s*(?:个|条|点|句|遍|次|项|方面))"
    r"[^，。！？]{1,32}|"
    r"(?:只|仅)(?:想|要|需|是)?(?:再|先)?(?:比较).{0,24}"
    r"(?:一点|这个|该|这一|其中|单个)|"
    r"(?:不要|别|不需要)(?:再)?(?:引入|展开|重复|提|讲).{0,10}(?:其他|另一)"
)
DEPTH_CHANGE_PATTERN = re.compile(
    r"(?:现在|这次|请|直接).{0,10}(?:完整|详细|展开|全面).{0,10}(?:解释|说明|讲|回答)|"
    r"不用再出题|不要再出题|不用问我|不要问我"
)
FULL_EXPLANATION_PATTERN = re.compile(
    r"(?:完整|详细|全面|展开)(?:地)?(?:解释|说明|讲|回答)|(?:解释|说明)(?:得)?(?:完整|详细)"
)
NEGATED_FULL_PATTERN = re.compile(
    r"(?:不|别|不要|不得|无需|不用|不需要).{0,8}(?:完整|详细|全面).{0,8}(?:解释|说明|讲|回答)|"
    r"(?:不|别|不要|不得|无需|不用|不需要).{0,8}(?:解释|说明|讲).{0,8}(?:完整|详细|全面)"
)
ACCURACY_PATTERN = re.compile(
    r"(?:不要|不得|不能|别).{0,6}(?:编造|虚构|猜测|臆测)|忠于教材|不要猜测|不得猜测"
)


def _last(history, role: str, *, skip: int = 0) -> str:
    found = 0
    for row in reversed(history or ()):
        if not isinstance(row, dict) or row.get("role") != role:
            continue
        content = row.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        if found == skip:
            return content.strip()
        found += 1
    return ""


def followup_directive(message: str, history) -> str:
    """Return extra prompt text for an explicit follow-up, or an empty string."""

    if not isinstance(message, str) or not message.strip():
        return ""
    previous_user = _last(history, "user")
    previous_assistant = _last(history, "assistant")
    lines: list[str] = []

    if SIMPLIFY_PATTERN.search(message) and previous_assistant:
        lines.append(
            "本轮是追问：'没听懂/换个说法/再简单点'指上一轮助教解释，不是末尾检查题。"
            "只简化该解释，不得改答检查题，也不得换新知识点或另出新题。"
        )
        lines.append("上一轮助教解释（本轮简化对象）：" + previous_assistant[:800])

    if COMPARE_FOLLOWUP_PATTERN.search(message):
        if NARROW_SCOPE_PATTERN.search(message):
            lines.append(
                "本轮明确缩小范围：只回答用户点名的对象；上一轮的其他对象只用于指代，"
                "不重复、不展开、不重新比较。"
            )
        else:
            lines.append(
                "本轮追问沿用上一轮对象，不扩大范围，也不舍弃已确认的一方。"
            )
        if previous_user:
            lines.append("上一轮对象与要求（仅作指代依据）：" + previous_user[:800])

    if DEPTH_CHANGE_PATTERN.search(message) and previous_assistant:
        lines.append(
            "本轮明确改变了解答深度：按当前完整解释或仅提示要求回答；"
            "上一轮仅提示约束失效，不得继续沿用。"
        )

    if ACCURACY_PATTERN.search(message):
        lines.append(
            "本轮'不要编造数据/不要猜测/忠于教材'是准确性要求，不是仅提示；"
            "明确要求完整解释时仍须完整解释全部对象。"
        )

    return "\n".join(lines)


__all__ = [
    "ACCURACY_PATTERN",
    "COMPARE_FOLLOWUP_PATTERN",
    "DEPTH_CHANGE_PATTERN",
    "FULL_EXPLANATION_PATTERN",
    "NARROW_SCOPE_PATTERN",
    "NEGATED_FULL_PATTERN",
    "SIMPLIFY_PATTERN",
    "followup_directive",
]
