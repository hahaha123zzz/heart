"""Small, session-only learning memory for the textbook chat demo.

This module reuses the shared StudentState and ShortTermTeachingPlan contracts.
It does not infer mastery from a student's self-report or lack of confidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Literal

from .contracts import StudentState
from .student_state import StudentSignal, build_student_state
from .teaching_plan import PlanStep, ShortTermTeachingPlan


FeedbackKind = Literal["stuck", "understood", "attempt", "other"]
AnswerEvaluation = Literal["correct", "partial", "incorrect", "uncertain"]


def classify_feedback(text: str, *, awaiting_answer: bool) -> FeedbackKind:
    normalized = re.sub(r"\s+", "", text.strip().lower())
    if any(marker in normalized for marker in (
        "不知道", "不懂", "没懂", "没听懂", "不会", "不清楚", "看不懂", "没思路",
    )):
        return "stuck"
    if any(marker in normalized for marker in ("懂了", "明白了", "理解了", "会了")):
        return "understood"
    if awaiting_answer and normalized and not any(
        marker in normalized for marker in (
            "？", "?", "为什么", "怎么", "请解释", "换个", "换一", "跳过",
            "暂停", "复习", "总结", "练习", "提示", "给我一道题",
        )
    ):
        return "attempt"
    return "other"


def _new_plan(topic_key: str) -> ShortTermTeachingPlan:
    return ShortTermTeachingPlan(
        id=f"demo:{topic_key}",
        knowledge_point_id=topic_key,
        steps=(
            PlanStep("diagnose", "diagnose", "发现学生已有的前置知识"),
            PlanStep("teach", "teach", "学生能解释一个基础概念"),
            PlanStep("check", "check", "学生能独立回答一题"),
        ),
    )


@dataclass
class TopicProgress:
    key: str
    query: str
    plan: ShortTermTeachingPlan
    signals: list[StudentSignal] = field(default_factory=list)
    stuck_count: int = 0
    pending_question: str | None = None

    @property
    def student_state(self) -> StudentState:
        return build_student_state(self.signals, preferences={"response_length": "CONCISE"})

    def observe(
        self,
        text: str,
        *,
        evaluation: AnswerEvaluation | None = None,
    ) -> FeedbackKind:
        kind = classify_feedback(text, awaiting_answer=self.pending_question is not None)
        self.pending_question = None
        ref = f"demo-turn-{len(self.signals) + 1}"
        if kind == "stuck":
            self.stuck_count += 1
            self.signals.append(StudentSignal(
                knowledge_point_id=self.key, confidence=0.2,
                source_ref=ref,
            ))
            if self.plan.current_step_index == 0:
                self.plan = replace(self.plan, current_step_index=1)
        elif kind == "understood":
            self.stuck_count = 0
            self.signals.append(StudentSignal(
                knowledge_point_id=self.key, confidence=0.7,
                source_ref=ref,
            ))
        elif kind == "attempt" and evaluation == "correct":
            self.stuck_count = 0
            self.signals.append(StudentSignal(
                knowledge_point_id=self.key,
                mastery=0.6 if not any(
                    signal.mastery is not None and signal.mastery >= 0.6
                    for signal in self.signals
                ) else 0.8,
                source_ref=ref,
            ))
            if self.plan.current_step_index < len(self.plan.steps) - 1:
                self.plan = replace(self.plan, current_step_index=self.plan.current_step_index + 1)
            else:
                self.plan = replace(self.plan, status="completed")
        elif kind == "attempt" and evaluation in ("incorrect", "partial"):
            self.stuck_count += 1
            self.signals.append(StudentSignal(
                knowledge_point_id=self.key, mastery=0.2 if evaluation == "incorrect" else None,
                source_ref=ref,
            ))
        return kind

    def record_reply(self, answer: str) -> None:
        questions = re.findall(r"[^。！\n？?]*[？?]", answer)
        self.pending_question = questions[-1].strip() if questions else None


@dataclass
class DemoLearningSession:
    topics: dict[str, TopicProgress] = field(default_factory=dict)
    active_topic_key: str | None = None

    @property
    def active(self) -> TopicProgress | None:
        return self.topics.get(self.active_topic_key or "")

    def activate(self, topic_key: str, query: str) -> TopicProgress:
        if topic_key not in self.topics:
            self.topics[topic_key] = TopicProgress(topic_key, query, _new_plan(topic_key))
        self.active_topic_key = topic_key
        return self.topics[topic_key]

    def reset(self) -> None:
        self.topics.clear()
        self.active_topic_key = None
