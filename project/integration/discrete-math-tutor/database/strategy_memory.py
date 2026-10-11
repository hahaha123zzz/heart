"""教学观察存取：来源过滤在数据库查询之前限定学生与知识点。"""
from sqlalchemy import select
from database.database import session_scope
from database.models import StrategyObservationRow, LearningEventRow, EventEvidenceRow, EvidenceRow


class StrategyMemoryRepository:
    def recent_teaching_moves(self, student_id, limit=5):
        with session_scope() as session:
            rows=session.scalars(select(LearningEventRow).where(
                LearningEventRow.student_id==student_id, LearningEventRow.event_type=="chat_turn",
                LearningEventRow.status=="committed").order_by(
                LearningEventRow.created_at.desc(),LearningEventRow.id.desc()).limit(limit)).all()
            return [r.payload["instructional_move"] for r in reversed(rows) if r.payload.get("instructional_move")]

    def record_strategy_observation(self, student_id, point, event_id, previous, decision, before_mastery, after_mastery):
        with session_scope() as session:
            current=session.get(LearningEventRow,event_id)
            if not current or current.student_id!=student_id or current.knowledge_point!=point or current.status!="committed":
                raise ValueError("策略观察必须属于当前学生已提交事件")
            old=session.scalar(select(StrategyObservationRow).where(StrategyObservationRow.observation_event_id==event_id))
            if old:
                return
            teacher=session.get(LearningEventRow,previous["id"]) if previous else None
            if teacher and (teacher.student_id!=student_id or teacher.knowledge_point!=point or teacher.status!="committed"):
                raise ValueError("教学来源归属不一致")
            payload=teacher.payload if teacher else {}
            context=payload.get("teaching_context") or {}
            links=session.execute(select(EventEvidenceRow,EvidenceRow).join(
                EvidenceRow, EventEvidenceRow.evidence_id==EvidenceRow.id).where(
                EventEvidenceRow.event_id==event_id)).all()
            grounded=next((link for link,evidence in links if link.independent and link.source_quote
                and link.source_quote in current.payload.get("content","")
                and evidence.evidence_type in ("conceptual_understanding","partial","misconception")),None)
            outcome="unknown"
            reason="未形成可归因的独立测量"
            if teacher and context and decision.independent and decision.eligible and grounded:
                delta=after_mastery-before_mastery
                outcome="progress" if delta>=.08-1e-9 else "regression" if delta<=-.08+1e-9 else "unknown"
                reason=f"独立作答后的掌握估计变化 {delta:+.3f}；仅为关联观察，不证明策略因果效果"
            elif not teacher or not context:
                reason="无同知识点的相邻教学来源，或旧事件缺少教学上下文"
            session.add(StrategyObservationRow(student_id=student_id,knowledge_point=point,
                observation_event_id=event_id,teaching_event_id=teacher.id if teacher else None,
                evidence_id=grounded.evidence_id if grounded else None,
                instructional_move=payload.get("instructional_move", ""),
                difficulty=context.get("difficulty","unknown"),hint_level=context.get("hint_level",0),
                outcome=outcome,verification=grounded.verification if grounded else "unmeasured",reason=reason))
            session.flush()

    def strategy_observations(self, student_id, point):
        with session_scope() as session:
            rows=session.scalars(select(StrategyObservationRow).where(
                StrategyObservationRow.student_id==student_id,
                StrategyObservationRow.knowledge_point==point).order_by(StrategyObservationRow.id)).all()
            result=[]
            for row in rows:
                current=session.get(LearningEventRow,row.observation_event_id)
                teacher=session.get(LearningEventRow,row.teaching_event_id) if row.teaching_event_id else None
                if not current or current.status!="committed" or (teacher and teacher.status!="committed"):
                    continue
                result.append({c.name:getattr(row,c.name) for c in row.__table__.columns if c.name!="created_at"})
            return result
