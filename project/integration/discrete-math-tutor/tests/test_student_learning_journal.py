"""任务 5：隔离 PostgreSQL 内的凭证归属与同步边界。"""
import os
from datetime import datetime
from unittest.mock import patch
from uuid import uuid4
import pytest

@pytest.fixture(scope="module")
def db():
    from tests.pg_support import temp_databases
    with temp_databases("heart_task5_journal") as env, patch.dict(os.environ, env):
        from database.database import engine, session_scope
        from database.models import Base
        Base.metadata.create_all(engine)
        yield session_scope
        engine.dispose()

def make_receipt(db, *, published=True, catalog="current", actor="user-a"):
    from database.models import Student, AssessmentJobRow, LearningEventRow, EvidenceRow, EventEvidenceRow
    job_id=str(uuid4());event_id=str(uuid4())
    with db() as session:
        if session.get(Student, actor) is None:
            session.add(Student(student_id=actor, account_type="real"));session.flush()
        job=AssessmentJobRow(id=job_id,student_id=actor,vendor_user_id="vendor-"+actor,
            source_id="fixture-"+uuid4().hex,input_hash=uuid4().hex,rule_version="fixture-v1",status="completed", input={"catalog_version":catalog,"targets":[]},
            result={"publication_status":"published" if published else "pending","vendor_evidence_id":"native-proof",
                    "judgment":{"knowledge_point_id":"point-1"}})
        session.add(job)
        if published:
            event=LearningEventRow(id=event_id, student_id=actor, source_key="vendor-assessment:"+job_id,
                knowledge_point="point-1",event_type="vendor_assessment",status="synced",
                payload={"vendor_user_id":"vendor-"+actor,"job_id":job_id,"vendor_evidence_id":"native-proof","assessed_mastered":False,"learning_stage":"practiced_with_help"})
            proof=EvidenceRow(student_id=actor,knowledge_point="point-1",evidence_type="vendor_assessment",content="{}")
            session.add_all([event,proof]);session.flush()
            session.add(EventEvidenceRow(event_id=event_id,evidence_id=proof.id,observation_key="vendor-result",
                verification="vendor_recorded",independent=False,source_quote="这条原始作答有辅助"))
            job.result={**job.result,"evidence_id":proof.id}
    return job_id

def query(job_id, actor="user-a"):
    from integrations.deeptutor.learning_projection import assessment_evidence
    with patch("integrations.deeptutor.learning_projection.confirmed_catalog",return_value=({"point-1":{}},"current")):
        return assessment_evidence(actor,"vendor-"+actor,job_id)

def test_published_receipt_requires_actual_owned_event_and_exposes_no_old_legacy_evidence(db):
    job=make_receipt(db)
    result=query(job)
    assert result["catalog_current"] and result["evidence"]["source_quote"]=="这条原始作答有辅助"
    assert not result["evidence"]["assessed_mastered"]
    assert result["misconceptions"]==[]
    assert query(job,"user-b") is None
    from database.models import AssessmentJobRow
    with db() as session:
        row=session.get(AssessmentJobRow,job)
        row.vendor_user_id="another-vendor-identity"
    assert query(job) is None

def test_pending_and_old_catalog_are_not_presented_as_current_synced_mastery(db):
    pending=query(make_receipt(db,published=False))
    assert pending["publication_status"]=="pending" and pending["evidence"] is None
    old=query(make_receipt(db,catalog="old"))
    assert old["evidence"] is not None and not old["catalog_current"]

def test_mislinked_receipt_cannot_expose_another_students_quote(db):
    from database.models import AssessmentJobRow
    first=make_receipt(db);second=make_receipt(db,actor="user-c")
    with db() as session:
        a=session.get(AssessmentJobRow,first);b=session.get(AssessmentJobRow,second)
        a.result={**a.result,"evidence_id":b.result["evidence_id"]}
    assert query(first)["evidence"] is None

def test_related_reassessment_history_is_bounded_but_completed_result_keeps_priority(db):
    from database.models import AssessmentJobRow
    from integrations.deeptutor.assessment_jobs import recent_jobs
    job=make_receipt(db,published=False,actor="user-limit")
    with db() as session:
        session.add(AssessmentJobRow(id=str(uuid4()), student_id="user-limit", vendor_user_id="vendor-user-limit",
            source_id="fixture-"+uuid4().hex, input_hash=uuid4().hex, rule_version="fixture-v1", status="completed",
            input={"reassessment":{"original_job_id":job,"reason":"成功复评"}},
            result={"publication_status":"published","judgment":{"passed":False,"feedback":"原文不支持"}}))
        for index in range(35):
            session.add(AssessmentJobRow(id=str(uuid4()), student_id="user-limit", vendor_user_id="vendor-user-limit",
                source_id="fixture-"+uuid4().hex,input_hash=uuid4().hex,rule_version="fixture-v1",status="failed",input={"reassessment":{"original_job_id":job,"reason":"重试"}},result={}))
    result=recent_jobs("user-limit","vendor-user-limit")
    assert len(result["jobs"])==1 and result["jobs"][0]["reassessment"]["status"]=="completed"


def test_misconceptions_are_the_observations_of_this_receipt_not_current_or_legacy_status(db):
    from database.models import MisconceptionRow, MisconceptionObservationRow
    job=make_receipt(db,actor="user-observations")
    result=query(job,actor="user-observations");proof=result["evidence"]
    with db() as session:
        item=MisconceptionRow(student_id="user-observations",knowledge_point="point-1",type="变量混淆",status="resolved")
        legacy=MisconceptionRow(student_id="user-observations",knowledge_point="point-1",type="没有事件依据的旧记录",status="confirmed")
        session.add_all([item,legacy]);session.flush()
        session.add(MisconceptionObservationRow(student_id="user-observations",misconception_id=item.id,
            event_id=proof["event_id"],evidence_id=proof["id"],action="observe",outcome="supported",
            before_status="hypothesis",after_status="supported",quote_hash="fixture",reason="该次作答的支持依据"))
    result=query(job,actor="user-observations")
    assert len(result["misconceptions"])==1
    assert result["misconceptions"][0]["type"]=="变量混淆"
    assert result["misconceptions"][0]["status"]=="supported"
