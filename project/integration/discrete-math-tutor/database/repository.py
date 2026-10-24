"""Repository 层 —— 纯数据访问（ORM <-> 领域模型），不含业务规则。

Agents 永远不会直接看到本层：它们只用 MemoryManager。
本层被替换（例如换存储）时，上层代码不用改。
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from uuid import uuid4
from typing import Dict, List, Optional

from sqlalchemy import select

from database.database import session_scope
from database.memory_index import MemoryIndexRepository
from database.strategy_memory import StrategyMemoryRepository
from database.memory_jobs import MemoryJobRepository
from database.memory_management import MemoryManagementRepository
from database.exercise_skills import ExerciseSkillRepository
from database.models import (
    LearningEventRow,
    EventEvidenceRow,
    MemoryRevisionRow,
    ActiveStateRow,
    ConversationRow,
    EvidenceRow,
    FigureCitationRow,
    PDFCitationRow,
    KnowledgeStateRow,
    LearnerProfileRow,
    MisconceptionRow,
    MisconceptionObservationRow,
    StrategyObservationRow,
    MemoryControlRow,
    ExerciseSkillObservationRow,
    Student,
    TestBuildStateRow,
    TeachingPlanRow,
)
from models.learner_profile import LearnerProfile
from models.lesson_plan import LessonPlan, LessonStep
from models.misconception import Misconception
from models.student_state import MistakePattern, StudentState


def _step_id(index: int) -> str:
    return "S" + str(index)


class Repository(MemoryIndexRepository, StrategyMemoryRepository, MemoryJobRepository, MemoryManagementRepository, ExerciseSkillRepository):
    # ---- students ---------------------------------------------------------
    def clear_test_accounts_on_code_change(self, fingerprint: str) -> int:
        """Atomically purge test accounts only when the application code changes."""
        with session_scope() as session:
            marker = session.get(TestBuildStateRow, "agent_code")
            if marker is not None and marker.fingerprint == fingerprint:
                return 0
            test_rows = session.scalars(
                select(Student).where(Student.account_type == "test")
            ).all()
            for row in test_rows:
                session.delete(row)
            if marker is None:
                session.add(TestBuildStateRow(key="agent_code", fingerprint=fingerprint))
            else:
                marker.fingerprint = fingerprint
            return len(test_rows)

    def ensure_student(
        self,
        student_id: str,
        account_type: str = "production",
        expires_at: Optional[dt.datetime] = None,
    ) -> None:
        with session_scope() as session:
            if session.get(Student, student_id) is None:
                session.add(
                    Student(
                        student_id=student_id,
                        account_type=account_type,
                        expires_at=expires_at,
                    )
                )

    def delete_student(self, student_id: str) -> bool:
        with session_scope() as session:
            row = session.get(Student, student_id)
            if row is None:
                return False
            session.delete(row)  # 级联删除所有关联数据
            return True

    def list_expired(self, now: Optional[dt.datetime] = None) -> List[str]:
        now = now or dt.datetime.utcnow()
        with session_scope() as session:
            rows = (
                session.execute(
                    select(Student.student_id).where(
                        Student.account_type == "test",
                        Student.expires_at.is_not(None), Student.expires_at < now
                    )
                )
                .scalars()
                .all()
            )
            return list(rows)

    def get_account_type(self, student_id: str) -> Optional[str]:
        with session_scope() as session:
            row = session.get(Student, student_id)
            return row.account_type if row else None

    def get_latest_knowledge_point(self, student_id: str) -> Optional[str]:
        """最近一次教学计划对应的知识点（用于跨会话恢复学习目标）。"""
        with session_scope() as session:
            row = (
                session.execute(
                    select(TeachingPlanRow)
                    .where(TeachingPlanRow.student_id == student_id)
                    .order_by(TeachingPlanRow.id.desc())
                    .limit(1)
                )
                .scalar_one_or_none()
            )
            return row.knowledge_point if row else None

    def get_active_knowledge_point(self, student_id: str) -> Optional[str]:
        with session_scope() as session:
            row = session.get(ActiveStateRow, student_id)
            return row.knowledge_point if row and row.knowledge_point else None

    def set_active_knowledge_point(self, student_id: str, knowledge_point: str) -> None:
        with session_scope() as session:
            row = session.get(ActiveStateRow, student_id)
            if row is None:
                row = ActiveStateRow(student_id=student_id)
                session.add(row)
            row.knowledge_point = knowledge_point

    def list_knowledge_points(self, student_id: str) -> List[str]:
        with session_scope() as session:
            rows = (
                session.execute(
                    select(KnowledgeStateRow.knowledge_point).where(
                        KnowledgeStateRow.student_id == student_id
                    )
                )
                .scalars()
                .all()
            )
            return list(dict.fromkeys(rows))

    def list_learning_points(self, student_id: str) -> List[str]:
        """包括已有证据/误解但尚未创建知识状态的知识点。"""
        with session_scope() as session:
            query=select(KnowledgeStateRow.knowledge_point).where(KnowledgeStateRow.student_id==student_id).union(
                select(MisconceptionRow.knowledge_point).where(MisconceptionRow.student_id==student_id),
                select(EvidenceRow.knowledge_point).where(EvidenceRow.student_id==student_id))
            return list(session.scalars(query).all())

    # ---- learner profile --------------------------------------------------
    def get_profile(self, student_id: str) -> LearnerProfile:
        with session_scope() as session:
            row = session.get(LearnerProfileRow, student_id)
            if row is None:
                return LearnerProfile(student_id=student_id)
            return LearnerProfile(
                student_id=student_id,
                preferences=dict(row.preferences or {}),
                learning_behavior=dict(row.learning_behavior or {}),
                teaching_effectiveness=dict(row.teaching_effectiveness or {}),
            )

    def save_profile(self, profile: LearnerProfile) -> None:
        with session_scope() as session:
            row = session.get(LearnerProfileRow, profile.student_id)
            if row is None:
                row = LearnerProfileRow(student_id=profile.student_id)
                session.add(row)
            row.preferences = profile.preferences
            row.learning_behavior = profile.learning_behavior
            row.teaching_effectiveness = profile.teaching_effectiveness

    # ---- knowledge state --------------------------------------------------
    def get_knowledge_state(self, student_id: str, knowledge_point: str) -> StudentState:
        with session_scope() as session:
            row = (
                session.execute(
                    select(KnowledgeStateRow).where(
                        KnowledgeStateRow.student_id == student_id,
                        KnowledgeStateRow.knowledge_point == knowledge_point,
                    )
                )
                .scalar_one_or_none()
            )
            state = StudentState(
                student_id=student_id, current_concept=knowledge_point
            )
            if row is not None:
                state.mastery = row.mastery
                state.confidence = row.confidence
                state.metacognition = row.metacognition
                state.emotion = row.emotion
                state.turn_count = row.turn_count
                state.last_summary = row.last_summary or ""
                state.remaining_gap = row.remaining_gap or ""
                state.steps_mastery = dict(row.steps_mastery or {})
                state.mistake_patterns = [
                    MistakePattern(**item) for item in (row.mistake_patterns or [])
                ]
            return state

    def save_knowledge_state(
        self, student_id: str, knowledge_point: str, state: StudentState
    ) -> None:
        with session_scope() as session:
            row = (
                session.execute(
                    select(KnowledgeStateRow).where(
                        KnowledgeStateRow.student_id == student_id,
                        KnowledgeStateRow.knowledge_point == knowledge_point,
                    )
                )
                .scalar_one_or_none()
            )
            if row is None:
                row = KnowledgeStateRow(
                    student_id=student_id, knowledge_point=knowledge_point
                )
                session.add(row)
            row.mastery = state.mastery
            row.confidence = state.confidence
            row.metacognition = state.metacognition
            row.emotion = state.emotion
            row.turn_count = state.turn_count
            row.last_summary = state.last_summary
            row.remaining_gap = state.remaining_gap
            row.steps_mastery = dict(state.steps_mastery)
            row.mistake_patterns = [p.model_dump() for p in state.mistake_patterns]

    # ---- misconceptions ---------------------------------------------------
    def list_misconceptions(
        self, student_id: str, knowledge_point: str
    ) -> List[Misconception]:
        with session_scope() as session:
            rows = (
                session.execute(
                    select(MisconceptionRow)
                    .where(
                        MisconceptionRow.student_id == student_id,
                        MisconceptionRow.knowledge_point == knowledge_point,
                    )
                    .order_by(MisconceptionRow.id)
                )
                .scalars()
                .all()
            )
            return [self._to_misconception(r) for r in rows]

    def find_misconception(
        self, student_id: str, knowledge_point: str, key: str
    ) -> Optional[Misconception]:
        with session_scope() as session:
            row = (
                session.execute(
                    select(MisconceptionRow).where(
                        MisconceptionRow.student_id == student_id,
                        MisconceptionRow.knowledge_point == knowledge_point,
                        (MisconceptionRow.type == key)
                        | (MisconceptionRow.description == key),
                    )
                )
                .scalars()
                .first()
            )
            return self._to_misconception(row) if row else None

    def save_misconception(
        self, student_id: str, item: Misconception
    ) -> Misconception:
        with session_scope() as session:
            row = session.get(MisconceptionRow, item.id) if item.id else None
            if row is None:
                row = MisconceptionRow(
                    student_id=student_id, knowledge_point=item.knowledge_point
                )
                session.add(row)
            if row.student_id != student_id or row.knowledge_point != item.knowledge_point:
                raise ValueError("不能修改其他学生或知识点的误区")
            row.type = item.type
            row.description = item.description
            row.confidence = item.confidence
            row.evidence_count = item.evidence_count
            row.status = item.status
            session.flush()
            item.id = row.id
            return item

    def set_misconception_status(
        self, student_id: str, knowledge_point: str, status: str, mtype: Optional[str] = None
    ) -> int:
        with session_scope() as session:
            query = select(MisconceptionRow).where(
                MisconceptionRow.student_id == student_id,
                MisconceptionRow.knowledge_point == knowledge_point,
            )
            if mtype:
                query = query.where(MisconceptionRow.type == mtype)
            rows = session.execute(query).scalars().all()
            for row in rows:
                row.status = status
            return len(rows)

    @staticmethod
    def _to_misconception(row: MisconceptionRow) -> Misconception:
        return Misconception(
            id=row.id,
            knowledge_point=row.knowledge_point,
            type=row.type,
            description=row.description,
            confidence=row.confidence,
            evidence_count=row.evidence_count,
            status=row.status,
        )

    # ---- evidence ---------------------------------------------------------
    def add_evidence(
        self,
        student_id: str,
        knowledge_point: str,
        evidence_type: str,
        content: str,
        confidence: float,
        misconception_id: Optional[int] = None,
    ) -> int:
        with session_scope() as session:
            row = EvidenceRow(
                student_id=student_id,
                knowledge_point=knowledge_point,
                evidence_type=evidence_type,
                content=content,
                confidence=confidence,
                misconception_id=misconception_id,
            )
            session.add(row)
            session.flush()
            return row.id

    def link_evidence(self, evidence_id: int, misconception_id: int) -> None:
        with session_scope() as session:
            row = session.get(EvidenceRow, evidence_id)
            if row is not None:
                row.misconception_id = misconception_id

    def list_evidence(
        self, student_id: str, knowledge_point: Optional[str] = None
    ) -> List[Dict]:
        with session_scope() as session:
            query = select(EvidenceRow).where(EvidenceRow.student_id == student_id)
            if knowledge_point:
                query = query.where(EvidenceRow.knowledge_point == knowledge_point)
            rows = session.execute(query.order_by(EvidenceRow.id)).scalars().all()
            links = {r.evidence_id: r for r in session.scalars(
                select(EventEvidenceRow).where(EventEvidenceRow.evidence_id.in_([r.id for r in rows]))
            ).all()} if rows else {}
            return [
                {
                    "event_id": links[r.id].event_id if r.id in links else None,
                    "verification": links[r.id].verification if r.id in links else "legacy_unverified",
                    "independent": links[r.id].independent if r.id in links else False,
                    "source_quote": links[r.id].source_quote if r.id in links else "",
                    "id": r.id,
                    "knowledge_point": r.knowledge_point,
                    "evidence_type": r.evidence_type,
                    "content": r.content,
                    "confidence": r.confidence,
                    "misconception_id": r.misconception_id,
                }
                for r in rows
            ]

    # ---- conversations ----------------------------------------------------
    def get_conversation(self, student_id: str, limit: int = 20, session_id: str | None = None) -> List[Dict[str, str]]:
        with session_scope() as session:
            query = select(ConversationRow).where(ConversationRow.student_id == student_id)
            if session_id is not None:
                query = query.where(ConversationRow.session_id == session_id)
            rows = (
                session.execute(
                    query
                    .order_by(ConversationRow.id.desc())
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            return [{"role": r.role, "content": r.content} for r in reversed(rows)]

    def get_conversation_with_figures(self, student_id: str, limit: int = 40, session_id: str | None = None) -> list[dict]:
        with session_scope() as session:
            query = select(ConversationRow).where(ConversationRow.student_id == student_id)
            if session_id is not None:
                query = query.where(ConversationRow.session_id == session_id)
            rows = session.scalars(
                query
                .order_by(ConversationRow.id.desc())
                .limit(limit)
            ).all()
            ids = [row.id for row in rows]
            citations = {
                row.conversation_id: row.figure_ids
                for row in session.scalars(
                    select(FigureCitationRow).where(FigureCitationRow.conversation_id.in_(ids))
                ).all()
            } if ids else {}
            pdf_citations = {r.conversation_id:r.reference for r in session.scalars(
                select(PDFCitationRow).where(PDFCitationRow.conversation_id.in_(ids))).all()} if ids else {}
            return [
                {"id": row.id, "role": row.role, "content": row.content,
                 "selection_ref": pdf_citations.get(row.id),
                 "image_ref_ids": citations.get(row.id, [])}
                for row in reversed(rows)
            ]

    def append_conversation(
        self, student_id: str, role: str, content: str,
        figure_ids: list[str] | None = None,
        selection_ref: dict | None = None,
        session_id: str | None = None,
    ) -> int:
        with session_scope() as session:
            row = ConversationRow(student_id=student_id, session_id=session_id, role=role, content=content)
            session.add(row)
            session.flush()
            if selection_ref:
                session.add(PDFCitationRow(conversation_id=row.id, reference=selection_ref))
            if figure_ids:
                session.add(FigureCitationRow(
                    conversation_id=row.id, figure_ids=list(figure_ids)
                ))
            return row.id

    def attach_guide(self, student_id, conversation_id, guide):
        """只给当前学生的现有回答补图，不重建被删除的对话。"""
        with session_scope() as session:
            row = session.get(ConversationRow, conversation_id)
            if row is None or row.student_id != student_id or row.role != "assistant":
                return False
            citation = session.get(PDFCitationRow, conversation_id)
            if citation is None:
                session.add(PDFCitationRow(conversation_id=conversation_id, reference={"guided_visualization": guide}))
            else:
                citation.reference = dict(citation.reference or {}, guided_visualization=guide)
            return True

    # ---- teaching plan ----------------------------------------------------
    def get_lesson_plan(
        self, student_id: str, knowledge_point: str
    ) -> Optional[LessonPlan]:
        with session_scope() as session:
            rows = (
                session.execute(
                    select(TeachingPlanRow)
                    .where(
                        TeachingPlanRow.student_id == student_id,
                        TeachingPlanRow.knowledge_point == knowledge_point,
                    )
                    .order_by(TeachingPlanRow.step)
                )
                .scalars()
                .all()
            )
            if not rows:
                return None
            steps = [
                LessonStep(
                    step_id=_step_id(r.step),
                    objective=r.objective,
                    completion_criteria=r.completion_criteria,
                    target_mastery=r.target_mastery,
                    teaching_form=r.teaching_form,
                    suggested_strategy=r.suggested_strategy,
                )
                for r in rows
            ]
            current = next((_step_id(r.step) for r in rows if r.status == "IN_PROGRESS"), "")
            status = "completed" if rows and all(r.status == "MASTERED" for r in rows) else "in_progress"
            return LessonPlan(
                goal=knowledge_point,
                steps=steps,
                current_step=current,
                status=status,
            )

    def save_lesson_plan(
        self,
        student_id: str,
        knowledge_point: str,
        plan: LessonPlan,
        steps_mastery: Optional[Dict[str, float]] = None,
    ) -> None:
        steps_mastery = steps_mastery or {}
        with session_scope() as session:
            session.query(TeachingPlanRow).filter(
                TeachingPlanRow.student_id == student_id,
                TeachingPlanRow.knowledge_point == knowledge_point,
            ).delete()
            for index, step in enumerate(plan.steps, start=1):
                mastery = float(steps_mastery.get(step.step_id, 0.0))
                if mastery >= step.target_mastery:
                    status = "MASTERED"
                elif step.step_id == plan.current_step and plan.status != "completed":
                    status = "IN_PROGRESS"
                else:
                    status = "PENDING"
                session.add(
                    TeachingPlanRow(
                        student_id=student_id,
                        knowledge_point=knowledge_point,
                        step=index,
                        objective=step.objective,
                        completion_criteria=step.completion_criteria,
                        target_mastery=step.target_mastery,
                        mastery=mastery,
                        teaching_form=step.teaching_form,
                        suggested_strategy=step.suggested_strategy,
                        status=status,
                    )
                )

    # ---- 事件溯源与短事务工作单元 -----------------------------------------
    def unit_of_work(self):
        return session_scope(immediate=True)

    def memory_snapshot(self, student_id: str, point: str) -> dict:
        """用于版本比较的完整投影；不包含对话/原始事件，避免丢失审计记录。"""
        with session_scope() as session:
            session.flush()
            result = {}
            for model in (KnowledgeStateRow, MisconceptionRow, TeachingPlanRow, LearnerProfileRow, ActiveStateRow, MisconceptionObservationRow, StrategyObservationRow, MemoryControlRow, ExerciseSkillObservationRow):
                query = select(model).where(model.student_id == student_id)
                if hasattr(model, "knowledge_point") and model is not ActiveStateRow:
                    query = query.where(model.knowledge_point == point)
                rows = session.scalars(query).all()
                values = [{c.name: getattr(r, c.name) for c in model.__table__.columns
                           if c.name not in ("created_at", "updated_at")} for r in rows]
                result[model.__tablename__] = sorted(values, key=lambda v: json.dumps(v, sort_keys=True))
            return result

    def memory_token(self, student_id: str, point: str) -> str:
        value = json.dumps(self.memory_snapshot(student_id, point), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(value.encode()).hexdigest()

    def get_event(self, student_id: str, source_key: str) -> dict | None:
        with session_scope() as session:
            row = session.scalar(select(LearningEventRow).where(
                LearningEventRow.student_id == student_id, LearningEventRow.source_key == source_key))
            return self._event_dict(row) if row else None

    @staticmethod
    def _event_dict(row) -> dict:
        return {"id": row.id, "source_key": row.source_key, "event_type": row.event_type,
                "status": row.status, "knowledge_point": row.knowledge_point, "payload": row.payload}

    def record_event(self, student_id, source_key, point, event_type, payload, status="recorded", event_id=None):
        with session_scope() as session:
            old = self.get_event(student_id, source_key)
            if old:
                return old
            row = LearningEventRow(id=event_id or str(uuid4()), student_id=student_id,
                source_key=source_key, knowledge_point=point, event_type=event_type, payload=payload, status=status)
            session.add(row)
            session.flush()
            return self._event_dict(row)

    def add_event_evidence(self, event_id, point, evidence_type, content, confidence, observation_key,
                           verification="ai_provisional", independent=False, source_quote="", misconception_id=None):
        with session_scope() as session:
            event = session.get(LearningEventRow, event_id)
            if event is None or event.knowledge_point != point:
                raise ValueError("证据来源事件与知识点不一致")
            if misconception_id is not None:
                target = session.get(MisconceptionRow, misconception_id)
                if target is None or target.student_id != event.student_id or target.knowledge_point != point:
                    raise ValueError("误区证据的归属不一致")
            old = session.scalar(select(EventEvidenceRow).where(
                EventEvidenceRow.event_id == event_id, EventEvidenceRow.observation_key == observation_key))
            if old:
                return old.evidence_id
            evidence_id = self.add_evidence(event.student_id, point, evidence_type, content, confidence, misconception_id)
            session.add(EventEvidenceRow(event_id=event_id, evidence_id=evidence_id,
                observation_key=observation_key, verification=verification, independent=independent, source_quote=source_quote))
            session.flush()
            return evidence_id

    def add_revision(self, student_id, event_id, point, before, after):
        with session_scope() as session:
            session.add(MemoryRevisionRow(student_id=student_id, event_id=event_id,
                knowledge_point=point, before=before, after=after))

    def latest_learning_event(self, student_id, point):
        """只认实际最近事件；不能越过圈选讲解等行为误认独立作答。"""
        with session_scope() as session:
            row = session.scalar(select(LearningEventRow).where(
                LearningEventRow.student_id == student_id
            ).order_by(LearningEventRow.created_at.desc(), LearningEventRow.id.desc()).limit(1))
            if row and row.event_type == "chat_turn" and row.status == "committed" and row.knowledge_point == point:
                return self._event_dict(row)
            return None

    def link_event_conversations(self, event_id, conversation_ids):
        with session_scope() as session:
            row = session.get(LearningEventRow, event_id)
            row.payload = dict(row.payload, conversation_ids=conversation_ids)

    def record_misconception_observation(self, student_id, misconception_id, event_id, evidence_id,
                                        action, outcome, before_status, after_status, quote_hash, reason):
        with session_scope() as session:
            target=session.get(MisconceptionRow,misconception_id)
            event=session.get(LearningEventRow,event_id)
            evidence=session.get(EvidenceRow,evidence_id)
            if not target or not event or not evidence or any(
                row.student_id != student_id for row in (target,event,evidence)) or (
                target.knowledge_point != event.knowledge_point or target.knowledge_point != evidence.knowledge_point
                or evidence.misconception_id != misconception_id):
                raise ValueError("误区审计的来源或归属不一致")
            link=session.scalar(select(EventEvidenceRow).where(EventEvidenceRow.event_id==event_id, EventEvidenceRow.evidence_id==evidence_id))
            if link is None:
                raise ValueError("误区审计证据必须来自本次事件")
            old=session.scalar(select(MisconceptionObservationRow).where(
                MisconceptionObservationRow.event_id==event_id, MisconceptionObservationRow.misconception_id==misconception_id))
            if old:
                return
            session.add(MisconceptionObservationRow(student_id=student_id,misconception_id=misconception_id,
                event_id=event_id,evidence_id=evidence_id,action=action,outcome=outcome,
                before_status=before_status,after_status=after_status,quote_hash=quote_hash,reason=reason))
            session.flush()

    def misconception_counter_votes(self, student_id, misconception_id, action):
        with session_scope() as session:
            rows=session.scalars(select(MisconceptionObservationRow).where(
                MisconceptionObservationRow.student_id==student_id,
                MisconceptionObservationRow.misconception_id==misconception_id
            ).order_by(MisconceptionObservationRow.id)).all()
            # 支持、冲突或不同的纠正意图都会中断连续反证，审计记录不删除。
            votes=set()
            for row in rows:
                if row.action!=action or row.outcome not in ("pending","resolved","dismissed"):
                    votes.clear()
                else:
                    votes.add(row.quote_hash)
            return votes

    def set_event_assessments(self, student_id, event_id, assessments):
        with session_scope() as session:
            row=session.get(LearningEventRow,event_id)
            if row is None or row.student_id!=student_id:
                raise ValueError("不能修改其他学生的事件")
            row.payload=dict(row.payload,misconception_updates=assessments)
