"""当前学生的显式更正及按知识点删除；不推测旧记录归属。"""
from uuid import uuid4
from sqlalchemy import select, delete
from database.database import session_scope
from database.models import TruthTableRow, RelationRow
from database.models import (Student, KnowledgeStateRow, MisconceptionRow, EvidenceRow, LearningEventRow,
    ConversationRow, PDFCitationRow, TeachingPlanRow, ActiveStateRow, MemoryDocumentRow, MemoryRevisionRow,
    StrategyObservationRow, MemoryArtifactRow, MemoryControlRow, MemoryExclusionRow, MemoryChangeRow, ExerciseSkillObservationRow, LearningTaskRow, VisualizationRow)

from models.interaction_preferences import InteractionPreferences
PREFERENCE_KEYS=set(InteractionPreferences.model_fields)


class MemoryManagementRepository:
    def memory_source_excluded(self, student_id, kind, source_id):
        with session_scope() as session:
            return session.scalar(select(MemoryExclusionRow.id).where(MemoryExclusionRow.student_id==student_id,
                MemoryExclusionRow.source_kind==kind,MemoryExclusionRow.source_id==source_id)) is not None

    def exclude_exercise_memory(self, student_id, point, submission_id):
        """保留练习成绩，但禁止已删除知识点的晚到批改再次进入记忆。"""
        with session_scope(immediate=True) as session:
            if not self.memory_source_excluded(student_id, "exercise", submission_id):
                session.add(MemoryExclusionRow(student_id=student_id, knowledge_point=point,
                    source_kind="exercise", source_id=submission_id))
                session.flush()

    def memory_epoch(self, student_id, point):
        with session_scope() as session:
            row=session.scalar(select(MemoryControlRow).where(MemoryControlRow.student_id==student_id,MemoryControlRow.knowledge_point==point))
            return row.epoch if row else 0

    def memory_overview(self, student_id, point=None):
        if self.get_account_type(student_id) is None:
            raise LookupError("学生不存在")
        self.sync_memory_index(student_id)
        points=self.list_learning_points(student_id)
        with session_scope() as session:
            event_points=session.scalars(select(LearningEventRow.knowledge_point).where(LearningEventRow.student_id==student_id)).all()
            indexed_points=session.scalars(select(MemoryDocumentRow.knowledge_point).where(MemoryDocumentRow.student_id==student_id)).all()
            task_points=session.scalars(select(LearningTaskRow.knowledge_point).where(LearningTaskRow.student_id==student_id)).all()
            visualization_points=session.scalars(select(VisualizationRow.knowledge_point).where(VisualizationRow.student_id==student_id)).all()
            visualization_points += session.scalars(select(TruthTableRow.knowledge_point).where(TruthTableRow.student_id==student_id)).all()
            visualization_points += session.scalars(select(RelationRow.knowledge_point).where(RelationRow.student_id==student_id)).all()
            points=sorted(set(points)|{p for p in event_points+indexed_points+task_points+visualization_points if p})
            if point and point not in points:
                raise LookupError("知识点记忆不存在")
            profile=self.get_profile(student_id)
            changes=session.scalars(select(MemoryChangeRow).where(MemoryChangeRow.student_id==student_id,
                MemoryChangeRow.action=="set_preference").order_by(MemoryChangeRow.id)).all()
            explicit={r.item_key for r in changes}
            result={"preferences":[{"key":key,"value":value,"source":"explicit_user" if key in explicit else "legacy_unverified"}
                for key,value in profile.preferences.items()],"points":points,"detail":None,
                "scope":"本机测试账户；删除以知识点为单位。归属不明的旧对话不猜测删除，练习成绩单独保留。"}
            if point:
                events=session.scalars(select(LearningEventRow).where(LearningEventRow.student_id==student_id,
                    LearningEventRow.knowledge_point==point).order_by(LearningEventRow.created_at.desc()).limit(20)).all()
                result["detail"]={"point":point,"state":self.get_knowledge_state(student_id,point).model_dump(),
                    "misconceptions":[m.model_dump() for m in self.list_misconceptions(student_id,point)],
                    "evidence":self.list_evidence(student_id,point)[-20:],
                    "events":[{"id":r.id,"type":r.event_type,"status":r.status,"content":str(r.payload.get("content") or "")[:700]} for r in events],
                    "background_memory":self.background_memories(student_id,point),
                    "skills":self.skill_summary(student_id,point)}
            return result

    def set_explicit_preferences(self, student_id, values):
        if set(values)-PREFERENCE_KEYS or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not 0<=v<=1 for v in values.values()):
            raise ValueError("偏好值无效")
        with session_scope(immediate=True) as session:
            if session.get(Student,student_id) is None:
                raise LookupError("学生不存在")
            profile=self.get_profile(student_id);profile.preferences.update(values)
            self.save_profile(profile)
            for key in values:
                session.add(MemoryChangeRow(student_id=student_id,action="set_preference",item_key=key))
            return profile.preferences

    def forget_preference(self, student_id, key):
        if key not in PREFERENCE_KEYS:
            raise ValueError("未知偏好")
        with session_scope(immediate=True) as session:
            profile=self.get_profile(student_id)
            if key not in profile.preferences:
                raise LookupError("偏好不存在")
            profile.preferences.pop(key);self.save_profile(profile)
            session.execute(delete(MemoryChangeRow).where(MemoryChangeRow.student_id==student_id,MemoryChangeRow.item_key==key,
                MemoryChangeRow.action=="set_preference"))
            for row in session.scalars(select(MemoryRevisionRow).where(MemoryRevisionRow.student_id==student_id)):
                for field in ("before","after"):
                    snapshot=dict(getattr(row,field))
                    profiles=[dict(value) for value in snapshot.get("learner_profiles",[])]
                    for value in profiles:
                        prefs=dict(value.get("preferences") or {});prefs.pop(key,None);value["preferences"]=prefs
                    snapshot["learner_profiles"]=profiles;setattr(row,field,snapshot)
            session.add(MemoryChangeRow(student_id=student_id,action="forget_preference",item_key=key))

    def dispute_misconception(self, student_id, item_id, note):
        if not note.strip() or len(note)>1000:
            raise ValueError("请填写更正说明")
        with session_scope(immediate=True) as session:
            row=session.get(MisconceptionRow,item_id)
            if row is None or row.student_id!=student_id:
                raise LookupError("误区不存在")
            row.status="dismissed"
            event=self.record_event(student_id,"correction:"+str(uuid4()),row.knowledge_point,"user_memory_correction",
                {"content":note,"misconception_id":item_id,"source":"explicit_user"})
            self.add_event_evidence(event["id"],row.knowledge_point,"user_correction",note,0,
                "user_correction",verification="student_statement",independent=False,source_quote=note,misconception_id=item_id)
            state=session.scalar(select(KnowledgeStateRow).where(KnowledgeStateRow.student_id==student_id,
                KnowledgeStateRow.knowledge_point==row.knowledge_point))
            if state:
                state.last_summary="";state.remaining_gap=""
            session.add(MemoryChangeRow(student_id=student_id,knowledge_point=row.knowledge_point,
                action="dispute_misconception",item_key=str(item_id)))
            session.flush();self.sync_memory_index(student_id)
            return {"id":item_id,"status":"dismissed","event_id":event["id"],"verification":"student_statement"}

    def forget_learning_point(self, student_id, point):
        with session_scope(immediate=True) as session:
            self.memory_overview(student_id,point)  # 未知/其他学生知识点不产生副作用
            events=session.scalars(select(LearningEventRow).where(LearningEventRow.student_id==student_id,
                LearningEventRow.knowledge_point==point)).all()
            event_ids={r.id for r in events};conversation_ids=set();submission_ids=set()
            for row in events:
                payload=row.payload or {}
                conversation_ids.update(payload.get("conversation_ids") or [])
                if payload.get("conversation_id"):
                    conversation_ids.add(payload["conversation_id"])
                if payload.get("submission_id"):
                    submission_ids.add(payload["submission_id"])
            docs=session.scalars(select(MemoryDocumentRow).where(MemoryDocumentRow.student_id==student_id,
                MemoryDocumentRow.knowledge_point==point)).all()
            for row in docs:
                if row.source_kind=="conversation":
                    conversation_ids.add(int(row.source_id))
                if row.source_kind=="exercise":
                    submission_ids.add(row.source_id)
            citations=session.execute(select(PDFCitationRow,ConversationRow).join(ConversationRow,
                ConversationRow.id==PDFCitationRow.conversation_id).where(ConversationRow.student_id==student_id)).all()
            conversation_ids.update(row.conversation_id for row,conv in citations if (row.reference or {}).get("section_title")==point)
            for sid in submission_ids:
                old=session.scalar(select(MemoryExclusionRow).where(MemoryExclusionRow.student_id==student_id,
                    MemoryExclusionRow.source_kind=="exercise",MemoryExclusionRow.source_id==sid))
                if old is None:
                    session.add(MemoryExclusionRow(student_id=student_id,knowledge_point=point,source_kind="exercise",source_id=sid))
            misconception_ids=set(session.scalars(select(MisconceptionRow.id).where(MisconceptionRow.student_id==student_id,
                MisconceptionRow.knowledge_point==point)).all())
            conversation_ids.update(session.scalars(select(VisualizationRow.conversation_id).where(
                VisualizationRow.student_id==student_id,VisualizationRow.knowledge_point==point)).all())
            session.execute(delete(VisualizationRow).where(VisualizationRow.student_id==student_id,
                VisualizationRow.knowledge_point==point))
            conversation_ids.update(session.scalars(select(TruthTableRow.conversation_id).where(
                TruthTableRow.student_id==student_id, TruthTableRow.knowledge_point==point)).all())
            session.execute(delete(TruthTableRow).where(TruthTableRow.student_id==student_id,
                TruthTableRow.knowledge_point==point))
            conversation_ids.update(session.scalars(select(RelationRow.conversation_id).where(
                RelationRow.student_id==student_id,RelationRow.knowledge_point==point)).all())
            session.execute(delete(RelationRow).where(RelationRow.student_id==student_id,RelationRow.knowledge_point==point))
            session.execute(delete(ConversationRow).where(ConversationRow.student_id==student_id,ConversationRow.id.in_(conversation_ids)))
            # 删除原始事件自动级联任务、证据链接和观察；证据本体按知识点删除。
            for model in (LearningEventRow,EvidenceRow,MisconceptionRow,KnowledgeStateRow,TeachingPlanRow,
                          StrategyObservationRow,MemoryArtifactRow,MemoryDocumentRow,MemoryChangeRow,ExerciseSkillObservationRow):
                session.execute(delete(model).where(model.student_id==student_id,model.knowledge_point==point))
            session.execute(delete(MemoryRevisionRow).where(MemoryRevisionRow.student_id==student_id,MemoryRevisionRow.knowledge_point==point))
            # 其他知识点快照可能包含学生级误区审计或活跃点，移除这些副本。
            for row in session.scalars(select(MemoryRevisionRow).where(MemoryRevisionRow.student_id==student_id)):
                for field in ("before","after"):
                    snapshot=dict(getattr(row,field))
                    for key,values in snapshot.items():
                        if isinstance(values,list):
                            snapshot[key]=[value for value in values if value.get("knowledge_point")!=point
                                and value.get("misconception_id") not in misconception_ids and value.get("event_id") not in event_ids]
                    setattr(row,field,snapshot)
            active=session.get(ActiveStateRow,student_id)
            if active and active.knowledge_point==point:
                session.delete(active)
            control=session.scalar(select(MemoryControlRow).where(MemoryControlRow.student_id==student_id,
                MemoryControlRow.knowledge_point==point))
            if control is None:
                control=MemoryControlRow(student_id=student_id,knowledge_point=point,epoch=0);session.add(control)
            session.execute(delete(LearningTaskRow).where(LearningTaskRow.student_id==student_id,
                LearningTaskRow.knowledge_point==point))
            control.epoch+=1
            session.add(MemoryChangeRow(student_id=student_id,knowledge_point=point,action="forget_point"))
            session.flush();self.sync_memory_index(student_id)
            return {"ok":True,"point":point,"exercise_records_preserved":True}
