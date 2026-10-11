"""可租约领取的持久任务；所有模型工作均在短事务之外。"""
import datetime as dt
import hashlib
import json
from uuid import uuid4
from sqlalchemy import select, or_, and_
from database.database import session_scope
from database.models import LearningEventRow, StrategyObservationRow, EventEvidenceRow, EvidenceRow, MemoryJobRow, MemoryArtifactRow, ConversationRow
from models.memory_artifact import verified_content

MAX_ATTEMPTS=3
LEASE_SECONDS=90


def utcnow():
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def source_snapshot(session, job):
    event=session.get(LearningEventRow,job.event_id)
    if not event or event.student_id!=job.student_id or event.status!="committed" or event.event_type!="chat_turn":
        return None
    observation=session.scalar(select(StrategyObservationRow).where(StrategyObservationRow.observation_event_id==event.id))
    teacher=session.get(LearningEventRow,observation.teaching_event_id) if observation and observation.teaching_event_id else None
    if observation and observation.teaching_event_id and not teacher:
        return None
    if teacher and (teacher.status!="committed" or teacher.student_id!=job.student_id or teacher.knowledge_point!=event.knowledge_point):
        return None
    conversations=[]
    for original in [event]+([teacher] if teacher else []):
        ids=original.payload.get("conversation_ids") or []
        rows=[session.get(ConversationRow,conversation_id) for conversation_id in ids]
        if not rows or any(row is None or row.student_id!=job.student_id for row in rows):
            return None
        if not any(row.role=="user" and row.content==original.payload.get("content","") for row in rows):
            return None
        conversations.extend({"id":row.id,"role":row.role,"content":row.content} for row in rows)
    evidence=session.execute(select(EventEvidenceRow,EvidenceRow).join(EvidenceRow,EventEvidenceRow.evidence_id==EvidenceRow.id).where(
        EventEvidenceRow.event_id.in_([event.id]+([teacher.id] if teacher else []))).order_by(EventEvidenceRow.id)).all()
    def event_data(row):
        return {"id":row.id,"knowledge_point":row.knowledge_point,"payload":row.payload,"policy_version":row.policy_version}
    return {"event":event_data(event),"teaching_event":event_data(teacher) if teacher else None,"conversations":conversations,
        "observation":{c.name:getattr(observation,c.name) for c in observation.__table__.columns if c.name!="created_at"} if observation else None,
        "evidence":[{"id":e.id,"content":e.content,"type":e.evidence_type,"confidence":e.confidence,
            "event_id":link.event_id,"verification":link.verification,"independent":link.independent,"quote":link.source_quote} for link,e in evidence]}


def fingerprint(source):
    return hashlib.sha256(json.dumps(source,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


class MemoryJobRepository:
    def enqueue_memory_job(self, student_id, event_id):
        with session_scope() as session:
            event=session.get(LearningEventRow,event_id)
            if not event or event.student_id!=student_id or event.status!="committed":
                raise ValueError("只能为当前学生已提交回合创建任务")
            old=session.scalar(select(MemoryJobRow).where(MemoryJobRow.event_id==event_id,MemoryJobRow.kind=="turn_consolidation:v1"))
            if old:
                return old.id
            job=MemoryJobRow(id=str(uuid4()),student_id=student_id,event_id=event_id,ready_at=utcnow())
            session.add(job);session.flush()
            return job.id

    def claim_memory_job(self, now=None):
        now=now or utcnow()
        with session_scope(immediate=True) as session:
            jobs=session.scalars(select(MemoryJobRow).where(or_(
                and_(MemoryJobRow.status=="queued",MemoryJobRow.ready_at<=now),
                and_(MemoryJobRow.status=="running",MemoryJobRow.lease_until<=now)
            )).order_by(MemoryJobRow.ready_at,MemoryJobRow.id).limit(32)).all()
            for job in jobs:
                source=source_snapshot(session,job)
                if source is None:
                    job.status="canceled";job.last_error="source_invalid";continue
                if job.attempts>=MAX_ATTEMPTS:
                    job.status="failed";job.last_error="attempts_exhausted";continue
                job.status="running";job.attempts+=1;job.lease_token=str(uuid4())
                job.lease_until=now+dt.timedelta(seconds=LEASE_SECONDS);job.source_hash=fingerprint(source)
                session.flush()
                return {"id":job.id,"student_id":job.student_id,"token":job.lease_token,"source_hash":job.source_hash,"source":source}
            return None

    @staticmethod
    def _owned_lease(session, claim, now):
        job=session.get(MemoryJobRow,claim["id"])
        if not job or job.student_id!=claim["student_id"] or job.status!="running" or job.lease_token!=claim["token"] or not job.lease_until or job.lease_until<=now:
            return None
        return job

    def finish_memory_job(self, claim, notes, mode="rule", now=None):
        now=now or utcnow()
        with session_scope(immediate=True) as session:
            job=self._owned_lease(session,claim,now)
            if not job:
                return False
            source=source_snapshot(session,job)
            if source is None:
                job.status="canceled";job.last_error="source_invalid";return False
            if fingerprint(source)!=job.source_hash or claim["source_hash"]!=job.source_hash:
                job.status="queued" if job.attempts<MAX_ATTEMPTS else "failed"
                job.ready_at=now+dt.timedelta(seconds=5);job.last_error="source_changed";return False
            if mode not in ("rule","llm"):
                raise ValueError("未知摘要生成方式")
            content=verified_content(source,notes,mode)
            row=session.scalar(select(MemoryArtifactRow).where(MemoryArtifactRow.job_id==job.id))
            if row is None:
                row=MemoryArtifactRow(student_id=job.student_id,job_id=job.id,event_id=job.event_id,
                    knowledge_point=source["event"]["knowledge_point"],source_hash=job.source_hash,content=content)
                session.add(row)
            else:
                row.source_hash=job.source_hash;row.content=content
            job.status="completed";job.last_error="";job.lease_token="";job.lease_until=None
            session.flush();return True

    def fail_memory_job(self, claim, now=None):
        now=now or utcnow()
        with session_scope(immediate=True) as session:
            job=self._owned_lease(session,claim,now)
            if not job:
                return False
            job.status="failed" if job.attempts>=MAX_ATTEMPTS else "queued"
            job.ready_at=now+dt.timedelta(seconds=min(300,5*2**job.attempts))
            # 不保存模型异常原文，避免把配置/凭据带到业务数据。
            job.last_error="generation_failed";job.lease_token="";job.lease_until=None
            return True

    def replay_memory_job(self, student_id, job_id):
        with session_scope(immediate=True) as session:
            job=session.get(MemoryJobRow,job_id)
            if not job or job.student_id!=student_id or job.status not in ("failed","completed"):
                return False
            if source_snapshot(session,job) is None:
                job.status="canceled";return False
            job.status="queued";job.attempts=0;job.ready_at=utcnow();job.last_error=""
            return True

    def memory_job_status(self, student_id, job_id):
        with session_scope() as session:
            job=session.get(MemoryJobRow,job_id)
            if not job or job.student_id!=student_id:
                return None
            return {"id":job.id,"status":job.status,"attempts":job.attempts,"last_error":job.last_error}

    def background_memories(self, student_id, point, limit=2):
        with session_scope() as session:
            rows=session.execute(select(MemoryArtifactRow,MemoryJobRow).join(MemoryJobRow,MemoryArtifactRow.job_id==MemoryJobRow.id).where(
                MemoryArtifactRow.student_id==student_id,MemoryArtifactRow.knowledge_point==point,
                MemoryJobRow.status=="completed").order_by(MemoryArtifactRow.created_at.desc(),MemoryArtifactRow.id.desc()).limit(20)).all()
            result=[]
            for artifact,job in rows:
                source=source_snapshot(session,job)
                if source is None or fingerprint(source)!=artifact.source_hash:
                    continue
                result.append({"id":artifact.id,"event_id":artifact.event_id,"point":point,
                    "content":artifact.content,"verification":artifact.verification})
                if len(result)>=limit:
                    break
            return result
