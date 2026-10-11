"""ORM 模型 —— 7 张表（学生 / 画像 / 知识状态 / 误解 / 证据 / 对话 / 教学计划）。

设计要点：
- 全部外键 ON DELETE CASCADE -> 删除学生即级联清空，测试账户可彻底销毁；
- 误解生命周期（hypothesis→…→resolved）用 status 字段承载；
- evidence 是核心表：一切状态判断可溯源。
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _now() -> dt.datetime:
    return dt.datetime.utcnow()


class Student(Base):
    __tablename__ = "students"

    student_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_type: Mapped[str] = mapped_column(String(20), default="production")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    expires_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)


class TestBuildStateRow(Base):
    """Fingerprint for clearing only test accounts after a code update."""

    __tablename__ = "test_build_state"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))


class ResourceViewRow(Base):
    __tablename__ = "resource_views"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("students.student_id", ondelete="CASCADE"), index=True
    )
    chapter_id: Mapped[int] = mapped_column(Integer)
    section_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, index=True)


class QuizAttemptRow(Base):
    __tablename__ = "quiz_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("students.student_id", ondelete="CASCADE"), index=True
    )
    chapter_id: Mapped[int] = mapped_column(Integer)
    score: Mapped[int] = mapped_column(Integer)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, index=True)


class LearnerProfileRow(Base):
    __tablename__ = "learner_profiles"

    student_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("students.student_id", ondelete="CASCADE"),
        primary_key=True,
    )
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    learning_behavior: Mapped[dict] = mapped_column(JSON, default=dict)
    teaching_effectiveness: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class KnowledgeStateRow(Base):
    __tablename__ = "knowledge_states"
    __table_args__ = (
        UniqueConstraint("student_id", "knowledge_point", name="uq_student_point"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("students.student_id", ondelete="CASCADE"),
        index=True,
    )
    knowledge_point: Mapped[str] = mapped_column(String(128), default="")
    mastery: Mapped[float] = mapped_column(Float, default=0.5)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    metacognition: Mapped[float] = mapped_column(Float, default=0.5)
    emotion: Mapped[str] = mapped_column(String(32), default="neutral")
    turn_count: Mapped[int] = mapped_column(Integer, default=0)
    last_summary: Mapped[str] = mapped_column(Text, default="")
    remaining_gap: Mapped[str] = mapped_column(Text, default="")
    steps_mastery: Mapped[dict] = mapped_column(JSON, default=dict)  # {"S1": 0.8}
    mistake_patterns: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class MisconceptionRow(Base):
    __tablename__ = "misconceptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("students.student_id", ondelete="CASCADE"),
        index=True,
    )
    knowledge_point: Mapped[str] = mapped_column(String(128), default="")
    type: Mapped[str] = mapped_column(String(64), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="hypothesis")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class EvidenceRow(Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("students.student_id", ondelete="CASCADE"),
        index=True,
    )
    knowledge_point: Mapped[str] = mapped_column(String(128), default="")
    evidence_type: Mapped[str] = mapped_column(String(32), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    misconception_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("misconceptions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, index=True)


class ConversationRow(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("students.student_id", ondelete="CASCADE"),
        index=True,
    )
    role: Mapped[str] = mapped_column(String(16), default="user")
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, index=True)


class FigureCitationRow(Base):
    __tablename__ = "figure_citations"

    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True
    )
    figure_ids: Mapped[list[str]] = mapped_column(JSON, default=list)


class TeachingPlanRow(Base):
    __tablename__ = "teaching_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("students.student_id", ondelete="CASCADE"),
        index=True,
    )
    knowledge_point: Mapped[str] = mapped_column(String(128), default="")
    step: Mapped[int] = mapped_column(Integer, default=1)
    objective: Mapped[str] = mapped_column(Text, default="")
    completion_criteria: Mapped[str] = mapped_column(Text, default="")
    target_mastery: Mapped[float] = mapped_column(Float, default=0.8)
    mastery: Mapped[float] = mapped_column(Float, default=0.0)
    teaching_form: Mapped[str] = mapped_column(String(20), default="socratic")
    suggested_strategy: Mapped[str] = mapped_column(String(40), default="socratic_questioning")
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ActiveStateRow(Base):
    """学生当前活跃的知识点（可被 Conversation Router 切换）。

    知识点 = 可切换的状态，而不是 Tutor 的身份。旧知识点的教学计划保留在
    teaching_plans 表里，学生以后可以说"继续讲 X"来恢复。
    """

    __tablename__ = "active_state"

    student_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("students.student_id", ondelete="CASCADE"),
        primary_key=True,
    )
    knowledge_point: Mapped[str] = mapped_column(String(128), default="")
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class PDFCitationRow(Base):
    """选区引用单独存表，兼容已有对话表与旧数据。"""
    __tablename__ = 'pdf_citations'
    conversation_id: Mapped[int] = mapped_column(Integer, ForeignKey('conversations.id', ondelete='CASCADE'), primary_key=True)
    reference: Mapped[dict] = mapped_column(JSON, default=dict)


class ExerciseDraftRow(Base):
    __tablename__ = 'exercise_drafts'
    __table_args__ = (UniqueConstraint('student_id','question_id'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[str] = mapped_column(String(64), ForeignKey('students.student_id', ondelete='CASCADE'), index=True)
    question_id: Mapped[str] = mapped_column(String(64))
    version: Mapped[str] = mapped_column(String(64))
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class ExerciseSubmissionRow(Base):
    __tablename__ = 'exercise_submissions'
    __table_args__ = (UniqueConstraint('student_id','request_id'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    student_id: Mapped[str] = mapped_column(String(64), ForeignKey('students.student_id', ondelete='CASCADE'), index=True)
    request_id: Mapped[str] = mapped_column(String(64))
    question_id: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[str] = mapped_column(String(64))
    answers: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default='queued')
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class ExerciseHelpRow(Base):
    __tablename__ = 'exercise_help'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    student_id: Mapped[str] = mapped_column(String(64), ForeignKey('students.student_id', ondelete='CASCADE'), index=True)
    question_id: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[str] = mapped_column(String(64))
    part_id: Mapped[str] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(20))
    level: Mapped[int] = mapped_column(Integer)
    answers: Mapped[dict] = mapped_column(JSON)
    response: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class LearningEventRow(Base):
    """原始学习事件；来源可重复投递，不能重复形成证据。"""
    __tablename__ = "learning_events"
    __table_args__ = (UniqueConstraint("student_id", "source_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    student_id: Mapped[str] = mapped_column(String(64), ForeignKey("students.student_id", ondelete="CASCADE"), index=True)
    source_key: Mapped[str] = mapped_column(String(160))
    knowledge_point: Mapped[str] = mapped_column(String(128), default="")
    event_type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(32), default="recorded")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    policy_version: Mapped[str] = mapped_column(String(32), default="memory-v1")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, index=True)


class EventEvidenceRow(Base):
    """旁表为旧 evidence 增加出处和资格，不伪造旧记录来源。"""
    __tablename__ = "event_evidence"
    __table_args__ = (UniqueConstraint("event_id", "observation_key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_events.id", ondelete="CASCADE"), index=True)
    evidence_id: Mapped[int] = mapped_column(Integer, ForeignKey("evidence.id", ondelete="CASCADE"), unique=True)
    observation_key: Mapped[str] = mapped_column(String(256))
    verification: Mapped[str] = mapped_column(String(32), default="ai_provisional")
    independent: Mapped[bool] = mapped_column(default=False)
    source_quote: Mapped[str] = mapped_column(Text, default="")


class MemoryRevisionRow(Base):
    __tablename__ = "memory_revisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[str] = mapped_column(String(64), ForeignKey("students.student_id", ondelete="CASCADE"), index=True)
    event_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_events.id", ondelete="CASCADE"), unique=True)
    knowledge_point: Mapped[str] = mapped_column(String(128))
    before: Mapped[dict] = mapped_column(JSON)
    after: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class MemoryDocumentRow(Base):
    """可重建的记忆检索索引；原始事实保留在业务表。"""
    __tablename__ = "memory_documents"
    __table_args__ = (UniqueConstraint("student_id", "source_kind", "source_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[str] = mapped_column(String(64), ForeignKey("students.student_id", ondelete="CASCADE"), index=True)
    source_kind: Mapped[str] = mapped_column(String(32))
    source_id: Mapped[str] = mapped_column(String(64))
    knowledge_point: Mapped[str] = mapped_column(String(128), default="")
    content: Mapped[str] = mapped_column(Text)
    index_text: Mapped[str] = mapped_column(Text)
    source_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64))
    embedding_model: Mapped[str] = mapped_column(String(128), default="")
    embedding: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class MisconceptionObservationRow(Base):
    """同一原始事件对同一误区只形成一次状态判定。"""
    __tablename__ = "misconception_observations"
    __table_args__ = (UniqueConstraint("event_id", "misconception_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[str] = mapped_column(String(64), ForeignKey("students.student_id", ondelete="CASCADE"), index=True)
    misconception_id: Mapped[int] = mapped_column(Integer, ForeignKey("misconceptions.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_events.id", ondelete="CASCADE"), index=True)
    evidence_id: Mapped[int] = mapped_column(Integer, ForeignKey("evidence.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String(32))
    outcome: Mapped[str] = mapped_column(String(32))
    before_status: Mapped[str] = mapped_column(String(20))
    after_status: Mapped[str] = mapped_column(String(20))
    quote_hash: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class StrategyObservationRow(Base):
    """当前作答对上一轮教学的观察；不是因果效果估计。"""
    __tablename__ = "strategy_observations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[str] = mapped_column(String(64), ForeignKey("students.student_id", ondelete="CASCADE"), index=True)
    knowledge_point: Mapped[str] = mapped_column(String(128), index=True)
    observation_event_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_events.id", ondelete="CASCADE"), unique=True)
    teaching_event_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("learning_events.id", ondelete="CASCADE"), nullable=True)
    evidence_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("evidence.id", ondelete="CASCADE"), nullable=True)
    instructional_move: Mapped[str] = mapped_column(String(40), default="")
    difficulty: Mapped[str] = mapped_column(String(20), default="unknown")
    hint_level: Mapped[int] = mapped_column(Integer, default=0)
    outcome: Mapped[str] = mapped_column(String(20))
    verification: Mapped[str] = mapped_column(String(32), default="ai_provisional")
    reason: Mapped[str] = mapped_column(Text)
    policy_version: Mapped[str] = mapped_column(String(32), default="strategy-observation-v1")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class MemoryJobRow(Base):
    """持久后台任务；租约令牌阻止过期执行者写回。"""
    __tablename__ = "memory_jobs"
    __table_args__ = (UniqueConstraint("event_id", "kind"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    student_id: Mapped[str] = mapped_column(String(64), ForeignKey("students.student_id", ondelete="CASCADE"), index=True)
    event_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_events.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40), default="turn_consolidation:v1")
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    ready_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    lease_token: Mapped[str] = mapped_column(String(36), default="")
    lease_until: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    source_hash: Mapped[str] = mapped_column(String(64), default="")
    last_error: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class MemoryArtifactRow(Base):
    """可丢弃、可重建的摘录与反思，不能替代原始事实。"""
    __tablename__ = "memory_artifacts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[str] = mapped_column(String(64), ForeignKey("students.student_id", ondelete="CASCADE"), index=True)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("memory_jobs.id", ondelete="CASCADE"), unique=True)
    event_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_events.id", ondelete="CASCADE"))
    knowledge_point: Mapped[str] = mapped_column(String(128), index=True)
    source_hash: Mapped[str] = mapped_column(String(64))
    content: Mapped[dict] = mapped_column(JSON)
    verification: Mapped[str] = mapped_column(String(32), default="derived_candidate")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class MemoryControlRow(Base):
    __tablename__ = "memory_controls"
    __table_args__ = (UniqueConstraint("student_id", "knowledge_point"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[str] = mapped_column(String(64), ForeignKey("students.student_id", ondelete="CASCADE"), index=True)
    knowledge_point: Mapped[str] = mapped_column(String(128))
    epoch: Mapped[int] = mapped_column(Integer, default=0)


class MemoryExclusionRow(Base):
    __tablename__ = "memory_exclusions"
    __table_args__ = (UniqueConstraint("student_id", "source_kind", "source_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[str] = mapped_column(String(64), ForeignKey("students.student_id", ondelete="CASCADE"), index=True)
    knowledge_point: Mapped[str] = mapped_column(String(128))
    source_kind: Mapped[str] = mapped_column(String(32))
    source_id: Mapped[str] = mapped_column(String(64))


class MemoryChangeRow(Base):
    """用户显式变更的当前来源；删除时不保留旧正文。"""
    __tablename__ = "memory_changes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[str] = mapped_column(String(64), ForeignKey("students.student_id", ondelete="CASCADE"), index=True)
    knowledge_point: Mapped[str] = mapped_column(String(128), default="")
    action: Mapped[str] = mapped_column(String(40))
    item_key: Mapped[str] = mapped_column(String(128), default="")
    source: Mapped[str] = mapped_column(String(32), default="explicit_user")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class ExerciseSkillObservationRow(Base):
    """规则小题技能观测；估计由有来源的观测派生，不更新全章掌握度。"""
    __tablename__ = "exercise_skill_observations"
    __table_args__ = (UniqueConstraint("event_id", "part_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[str] = mapped_column(String(64), ForeignKey("students.student_id", ondelete="CASCADE"), index=True)
    event_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_events.id", ondelete="CASCADE"), index=True)
    knowledge_point: Mapped[str] = mapped_column(String(128), index=True)
    question_id: Mapped[str] = mapped_column(String(64))
    question_version: Mapped[str] = mapped_column(String(64))
    part_id: Mapped[str] = mapped_column(String(20))
    skill_id: Mapped[str] = mapped_column(String(64), index=True)
    skill_name: Mapped[str] = mapped_column(String(128))
    concept: Mapped[str] = mapped_column(String(128))
    mapping_version: Mapped[str] = mapped_column(String(64))
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    outcome: Mapped[str] = mapped_column(String(24))
    reason: Mapped[str] = mapped_column(String(256))
    diagnostic_targets: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
