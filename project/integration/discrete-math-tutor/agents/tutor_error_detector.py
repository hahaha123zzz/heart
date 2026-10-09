"""Tutor Error Detector —— 检测本轮教学是否出错，并触发状态回滚。

【自主实现】解决"AI 自己判断错后不会纠正、错误状态被永久固化"。
【自主衔接】检测逻辑与 State Updater 共用一次 LLM 调用：
State Updater 输出里带 tutor_error 字段，本模块负责解析并决定是否回滚。
"""

from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel

TUTOR_ERROR_TYPES = [
    "wrong_explanation",  # 讲解错误
    "misjudged_state",  # 误判学生状态
    "off_plan",  # 偏离教学计划
    "bad_question",  # 题目无效/太简单
]


class TutorErrorResult(BaseModel):
    detected: bool = False
    error_type: str = ""
    reason: str = ""
    rollback: bool = False


class TutorErrorDetector:
    def detect(self, update_data: Dict[str, Any]) -> TutorErrorResult:
        raw = update_data.get("tutor_error")
        if not isinstance(raw, dict):
            return TutorErrorResult()
        error_type = str(raw.get("error_type") or "")
        if error_type not in TUTOR_ERROR_TYPES:
            error_type = ""
        return TutorErrorResult(
            detected=bool(raw.get("detected")),
            error_type=error_type,
            reason=str(raw.get("reason") or ""),
            rollback=bool(raw.get("rollback")),
        )
