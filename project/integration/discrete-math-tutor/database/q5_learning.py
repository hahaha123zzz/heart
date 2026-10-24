"""Q5 first-batch persistence: paths, modules, objectives, progress, bindings.

Adapted from DeepTutor ``learning/models.py`` (commit
``6cf793bd868ba5ecbe64722936d4be8fab5a01df``, Apache-2.0) but stored in this
project's SQLAlchemy database.  The upstream account/session/JSON stores are
not copied.  Only the tables needed for the first batch are created here:
formal questions, attempts, mastery evidence, review and teacher review remain
Q5 follow-up work.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from database.models import Base


def _now() -> dt.datetime:
    return dt.datetime.utcnow()


class Q5PathRow(Base):
    __tablename__ = "q5_learning_paths"

    path_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    student_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("students.student_id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[str] = mapped_column(String(64), default="")
    kind: Mapped[str] = mapped_column(String(32), default="mastery_goal")
    name: Mapped[str] = mapped_column(String(200), default="")
    goal: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    plan_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    teaching_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    source_scope: Mapped[dict] = mapped_column(JSON, default=dict)
    current_objective_id: Mapped[str] = mapped_column(String(64), default="")
    current_module_id: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Q5ModuleRow(Base):
    __tablename__ = "q5_learning_modules"

    module_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    path_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("q5_learning_paths.path_id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(200), default="")
    objective: Mapped[str] = mapped_column(Text, default="")
    pass_threshold: Mapped[float] = mapped_column(Float, default=0.7)


class Q5ObjectiveRow(Base):
    __tablename__ = "q5_learning_objectives"
    __table_args__ = (UniqueConstraint("path_id", "module_id", "position", name="uq_q5_objective_position"),)

    objective_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    path_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("q5_learning_paths.path_id", ondelete="CASCADE"), index=True
    )
    module_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("q5_learning_modules.module_id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(200), default="")
    knowledge_type: Mapped[str] = mapped_column(String(16), default="concept")
    prerequisite_ids: Mapped[list] = mapped_column(JSON, default=list)
    source_refs: Mapped[list] = mapped_column(JSON, default=list)
    required_visual_tasks: Mapped[list] = mapped_column(JSON, default=list)


class Q5ProgressRow(Base):
    __tablename__ = "q5_learning_progress"
    __table_args__ = (UniqueConstraint("path_id", "objective_id", name="uq_q5_progress"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    path_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("q5_learning_paths.path_id", ondelete="CASCADE"), index=True
    )
    objective_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("q5_learning_objectives.objective_id", ondelete="CASCADE"), index=True
    )
    explained: Mapped[bool] = mapped_column(Boolean, default=False)
    understood: Mapped[bool] = mapped_column(Boolean, default=False)
    explanation_summary: Mapped[str] = mapped_column(Text, default="")
    explained_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    understood_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Q5BindingRow(Base):
    __tablename__ = "q5_learning_bindings"
    __mapper_args__ = {"eager_defaults": False}

    student_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("students.student_id", ondelete="CASCADE"), primary_key=True
    )
    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    active_path_id: Mapped[str] = mapped_column(String(64), default="")
    mode: Mapped[str] = mapped_column(String(16), default="outline")
    teaching_strategy: Mapped[str] = mapped_column(String(20), default="probe_first")
    # 旧库读取不隐式选取新列；启用本次安排前必须显式执行增量迁移。
    session_plan: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, deferred=True, server_default=text('NULL'))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Q5CommandRow(Base):
    __tablename__ = "q5_learning_commands"
    __table_args__ = (UniqueConstraint("student_id", "command_id", name="uq_q5_command"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("students.student_id", ondelete="CASCADE"), index=True
    )
    command_id: Mapped[str] = mapped_column(String(80))
    command_type: Mapped[str] = mapped_column(String(40), default="")
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


def ensure_q5_schema(engine=None) -> None:
    """Create only the Q5 first-batch tables; safe to call repeatedly."""
    from database.database import engine as default_engine

    Base.metadata.create_all(engine or default_engine)


__all__ = [
    "ensure_q5_schema",
    "Q5PathRow",
    "Q5ModuleRow",
    "Q5ObjectiveRow",
    "Q5ProgressRow",
    "Q5BindingRow",
    "Q5CommandRow",
]
