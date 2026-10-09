"""Deterministic short-turn signals; never infer mastery from 'I don't know'."""

from __future__ import annotations

from typing import Iterable


STUCK_PHRASES = ("不知道", "不懂", "没懂", "不会", "没思路", "看不懂", "不清楚")
UNDERSTOOD_PHRASES = ("懂了", "明白了", "理解了")


def is_stuck(text: str) -> bool:
    return any(phrase in text for phrase in STUCK_PHRASES)


def is_self_report_understood(text: str) -> bool:
    return not is_stuck(text) and any(phrase in text for phrase in UNDERSTOOD_PHRASES)


def consecutive_stuck(history: Iterable[dict[str, str]], latest: str) -> int:
    if not is_stuck(latest):
        return 0
    count = 1
    for item in reversed(list(history)):
        if item.get("role") != "user":
            continue
        if not is_stuck(item.get("content", "")):
            break
        count += 1
    return count
