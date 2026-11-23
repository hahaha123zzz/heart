"""按已确认教材目录展示厂家同步快照，图谱实体映射另行确认。"""
from datetime import datetime, timezone

from sqlalchemy import Float, cast, func, select

from database.database import session_scope
from database.models import AssessmentJobRow as Job, LearningEventRow as Event
from integrations.deeptutor.assessment_intake import confirmed_catalog


def chapter_progress(student_id, vendor_user_id, chapter):
    catalog, version = confirmed_catalog()
    points = sorted((point for point in catalog.values() if point.get("chapter_id") == chapter),
                    key=lambda point: (point.get("section_id", 0), point["id"]))
    if not points:
        return {"catalog_available": bool(catalog), "points": []}
    ids = [point["id"] for point in points]
    kp = Job.result["judgment"]["knowledge_point_id"].as_string()
    publication = Job.result["publication_status"].as_string()
    active = (Job.student_id == student_id, Job.vendor_user_id == vendor_user_id,
              Job.status == "completed", kp.in_(ids), Job.input["catalog_version"].as_string() == version)
    with session_scope() as session:
        ranked = (select(Event.knowledge_point, Event.payload, Event.created_at,
            func.row_number().over(partition_by=Event.knowledge_point,
                order_by=(Event.created_at.desc(), Event.id.desc())).label("position"))
            .join(Job, Event.source_key == func.concat("vendor-assessment:", Job.id))
            .where(*active, publication == "published", Event.student_id == student_id,
                   Event.event_type == "vendor_assessment", Event.status == "synced",
                   Event.knowledge_point == kp, Event.payload["vendor_user_id"].as_string() == vendor_user_id,
                   Event.payload["job_id"].as_string() == Job.id)
            .subquery())
        rows = session.execute(select(ranked.c.knowledge_point, ranked.c.payload, ranked.c.created_at)
                               .where(ranked.c.position == 1)).all()
        pending = set(session.execute(select(kp, publication).where(*active,
            publication.in_(("pending", "blocked"))).distinct()).all())
        practice_ranked = select(Event.knowledge_point, Event.payload,
            func.row_number().over(partition_by=Event.knowledge_point, order_by=(
                cast(Event.payload["reviewed_at"].as_string(), Float).desc(), Event.id.desc())).label("position"))
        practice_ranked = practice_ranked.where(Event.student_id == student_id, Event.knowledge_point.in_(ids),
            Event.payload["vendor_user_id"].as_string() == vendor_user_id,
            Event.payload["catalog_version"].as_string() == version,
            Event.event_type == "vendor_practice_review", Event.status == "synced").subquery()
        practice = dict(session.execute(select(practice_ranked.c.knowledge_point, practice_ranked.c.payload)
                                       .where(practice_ranked.c.position == 1)).all())
    snapshots = {}
    for point_id, value, synced_at in rows:
        retention = value.get("retention") or {}
        due = retention.get("next_review_at")
        review_at = None
        if type(due) in (int, float):
            try:
                review_at = datetime.fromtimestamp(due, timezone.utc).isoformat()
            except (ValueError, OverflowError, OSError):
                pass
        snapshots[point_id] = {"assessed_mastered": value.get("assessed_mastered") is True,
            "learning_stage": value.get("learning_stage", ""), "next_review_at": review_at,
            "synced_at": synced_at.replace(tzinfo=timezone.utc).isoformat(),
            **{key:((value.get("assessment") or {}).get("visual_context") or {}).get(key, "") for key in ("mapping_version", "graph_release_id", "catalog_version", "rule_version")},
            "job_id": value.get("job_id", "")}
    return {"catalog_available": True, "points": [{"id": point["id"], "name": point["name"],
        "snapshot": snapshots.get(point["id"]),
        "practice_review": _review_summary(practice.get(point["id"])), "sync_pending": (point["id"], "pending") in pending,
        "sync_blocked": (point["id"], "blocked") in pending} for point in points]}



def _review_summary(payload):
    if payload is None:
        return None
    review = payload["review"]
    return {"correct": review["correct"], "self_report": review["self_report"],
            "assistance_status": (review.get("assistance") or {}).get("status", "not_verified"),
            "next_review_at": datetime.fromtimestamp(review["due_at"], timezone.utc).isoformat()}


def assessment_evidence(student_id, vendor_user_id, job_id):
    """按需读取单条已同步凭证，只接受当前账号的真实事件关联。"""
    from database.models import EvidenceRow as Evidence, EventEvidenceRow as Link
    from database.models import MisconceptionObservationRow as Observation, MisconceptionRow as Misconception
    catalog, catalog_version = confirmed_catalog()
    with session_scope() as session:
        job = session.scalar(select(Job).where(Job.id == job_id, Job.student_id == student_id,
                                               Job.vendor_user_id == vendor_user_id))
        if job is None:
            return None
        saved = job.result or {}
        point = (saved.get("judgment") or {}).get("knowledge_point_id", "")
        result = {"job_id": job_id, "catalog_available": bool(catalog), "publication_status": saved.get("publication_status", ""),
                  "catalog_current": bool(catalog) and point in catalog and job.input.get("catalog_version") == catalog_version,
                  "vendor_evidence_id": saved.get("vendor_evidence_id"), "evidence": None, "misconceptions": []}
        if job.status != "completed" or result["publication_status"] != "published":
            return result
        row = session.execute(select(Evidence, Link, Event).join(Link, Link.evidence_id == Evidence.id)
            .join(Event, Event.id == Link.event_id).where(Evidence.id == saved.get("evidence_id"),
                Evidence.student_id == student_id, Evidence.knowledge_point == point,
                Event.student_id == student_id, Event.knowledge_point == point, Event.status == "synced",
                Event.event_type == "vendor_assessment", Event.source_key == "vendor-assessment:" + job_id,
                Event.payload["vendor_user_id"].as_string() == vendor_user_id,
                Event.payload["job_id"].as_string() == job_id,
                Link.verification == "vendor_recorded", Link.observation_key == "vendor-result",
                Event.payload["vendor_evidence_id"].as_string() == saved.get("vendor_evidence_id"))).first()
        if row is None:
            return result
        evidence, link, event = row
        result["evidence"] = {"id": evidence.id, "event_id": event.id, "source_quote": link.source_quote,
            "verification": link.verification, "learning_stage": event.payload.get("learning_stage", ""),
            "assessed_mastered": event.payload.get("assessed_mastered") is True,
            "synced_at": event.created_at.replace(tzinfo=timezone.utc).isoformat()}
        observations = session.execute(select(Observation, Misconception).join(Misconception,
            Misconception.id == Observation.misconception_id).where(Observation.event_id == event.id,
                Observation.student_id == student_id, Observation.evidence_id == evidence.id,
                Misconception.student_id == student_id, Misconception.knowledge_point == point)
            .order_by(Observation.id.desc()).limit(20)).all()
        result["misconceptions"] = [{"id": observation.id, "type": item.type,
            "status": observation.after_status, "reason": observation.reason} for observation, item in observations]
        return result
