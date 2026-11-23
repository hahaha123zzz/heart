"""后台评估租约与凭据生命周期；不推断分数，不调用模型。"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from uuid import uuid4

from sqlalchemy import case, func, select, update

from database.database import session_scope
from database.models import AssessmentJobRow as Job, AssessmentQueueSetting as Setting
from integrations.deeptutor import model_credentials as credentials
from integrations.deeptutor import model_capabilities as capabilities

LEASE_SECONDS = 90
MAX_ATTEMPTS = 3
PENDING = ("queued", "claimed", "paused")
REASSESSMENT_ROOT = Job.input["reassessment"]["original_job_id"].as_string()


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _enabled(session, student_id):
    setting = session.get(Setting, student_id)
    return setting is None or setting.enabled


def credentials_changed(session, student_id, *, available, reason="credential_missing"):
    status = case((REASSESSMENT_ROOT.is_not(None), "queued"), else_="queued" if _enabled(session, student_id) else "paused") if available else "paused"
    session.execute(update(Job).where(Job.student_id == student_id, Job.status.in_(PENDING)).values(
        status=status, lease_token="", lease_until=None,
        last_error="" if available else reason))


def set_enabled(student_id, enabled):
    if type(enabled) is not bool:
        raise ValueError("invalid_evaluation_setting")
    with session_scope(immediate=True) as session:
        setting = session.get(Setting, student_id)
        if setting is None:
            session.add(Setting(student_id=student_id, enabled=enabled, revision=int(not enabled)))
        elif setting.enabled != enabled:
            setting.enabled = enabled
            setting.revision += 1
        if not enabled:
            session.execute(update(Job).where(Job.student_id == student_id, Job.status.in_(PENDING),
                REASSESSMENT_ROOT.is_(None)).values(
                status="cancelled", lease_token="", lease_until=None, last_error="evaluation_disabled"))
    return {"enabled": enabled}


def evaluation_control(student_id):
    with session_scope() as session:
        row=session.get(Setting,student_id)
        return {"enabled":row.enabled if row else True,"revision":row.revision if row else 0}


def get_enabled(student_id):
    with session_scope() as session:
        return {"enabled": _enabled(session, student_id)}



def _queue_state(student_id, vendor_user_id):
    config = credentials.read(student_id)
    if config is None: return "paused", "credential_missing"
    if not capabilities.assessment_ready(student_id, vendor_user_id, config["credential_version"]):
        return "paused", capabilities.pause_code(student_id, vendor_user_id, config["credential_version"])
    return "queued", ""

def enqueue(student_id, vendor_user_id, source_id, input_snapshot, rule_version):
    if not student_id or len(student_id) > 64 or not vendor_user_id or len(vendor_user_id) > 128:
        raise ValueError("invalid_assessment_owner")
    if not source_id or len(source_id) > 200 or not rule_version or len(rule_version) > 128:
        raise ValueError("invalid_assessment_source")
    encoded = json.dumps(input_snapshot, sort_keys=True, ensure_ascii=False, allow_nan=False)
    if not isinstance(input_snapshot, dict) or len(encoded.encode("utf-8")) > 65536:
        raise ValueError("invalid_assessment_input")
    digest = sha256(encoded.encode("utf-8")).hexdigest()
    with session_scope(immediate=True) as session:
        existing = session.scalar(select(Job).where(Job.student_id == student_id, Job.source_id == source_id))
        if existing:
            if (existing.input_hash, existing.rule_version, existing.vendor_user_id) != (digest, rule_version, vendor_user_id):
                raise ValueError("assessment_source_conflict")
            return None if existing.status == "cancelled" else existing.id
        job_id = str(uuid4())
        control=input_snapshot.get("evaluation_control")
        current=session.get(Setting,student_id)
        stale_control=control is not None and (not isinstance(control,dict) or control.get("enabled") is not True
            or type(control.get("revision")) is not int or control["revision"] != (current.revision if current else 0))
        if not _enabled(session, student_id) or stale_control:
            session.add(Job(id=job_id, student_id=student_id, vendor_user_id=vendor_user_id,
                source_id=source_id, input={}, input_hash=digest, rule_version=rule_version,
                status="cancelled", last_error="evaluation_disabled"))
            return None
        state, error = _queue_state(student_id, vendor_user_id)
        session.add(Job(id=job_id, student_id=student_id, vendor_user_id=vendor_user_id,
                        source_id=source_id, input=input_snapshot, input_hash=digest, rule_version=rule_version,
                        status=state, last_error=error))
        return job_id


def claim(student_id, *, now=None):
    now = now or _now()
    with session_scope(immediate=True) as session:
        # 未发送的过期领取可恢复；已标记发送的请求只能进入结果不明。
        session.execute(update(Job).where(Job.student_id == student_id, Job.status == "claimed",
            Job.lease_until <= now).values(status="queued", lease_token="", lease_until=None))
        session.execute(update(Job).where(Job.student_id == student_id, Job.status == "sent",
            Job.lease_until <= now).values(status="unknown", lease_until=None, last_error="outcome_unknown"))
        if credentials.read(student_id) is None:
            credentials_changed(session, student_id, available=False)
            return None
        if session.scalar(select(Job.id).where(Job.student_id == student_id, Job.status.in_(("claimed", "sent"))).limit(1)):
            return None
        query = select(Job).where(Job.student_id == student_id, Job.status == "queued", Job.ready_at <= now)
        if not _enabled(session, student_id):
            query = query.where(REASSESSMENT_ROOT.is_not(None))
        row = session.scalar(query.order_by(Job.created_at, Job.id).limit(1))
        if row is None:
            return None
        state, error = _queue_state(student_id, row.vendor_user_id)
        if state == "paused":
            capabilities._pause_pending(session, student_id, row.vendor_user_id, error)
            return None
        row.status, row.lease_token = "claimed", str(uuid4())
        row.lease_until = now + timedelta(seconds=LEASE_SECONDS)
        return {"id": row.id, "lease_token": row.lease_token}


def begin_send(student_id, job_id, lease_token, *, now=None):
    now = now or _now()
    with session_scope(immediate=True) as session:
        row = session.get(Job, job_id)
        if (row is None or row.student_id != student_id or row.status != "claimed"
                or not lease_token or row.lease_token != lease_token or row.lease_until <= now):
            return None
        if not _enabled(session, student_id) and not row.input.get("reassessment"):
            row.status, row.lease_token, row.lease_until = "cancelled", "", None
            return None
        try:
            config = credentials.read(student_id, decrypt=True)
        except RuntimeError:
            credentials_changed(session, student_id, available=False, reason="credential_unavailable")
            return None
        if config is None:
            credentials_changed(session, student_id, available=False)
            return None
        if not capabilities.assessment_ready(student_id, row.vendor_user_id, config["credential_version"]):
            capabilities._pause_pending(session, student_id, row.vendor_user_id, capabilities.pause_code(student_id, row.vendor_user_id, config["credential_version"]))
            return None
        # 先持久化发送边界；此后崩溃保守视为可能已计费，不能自动重发。
        row.status = "sent"
        row.attempts += 1
        row.lease_until = now + timedelta(seconds=LEASE_SECONDS)
        row.credential_version, row.used_model = config["credential_version"], config["model"]
        return {"id": row.id, "student_id": row.student_id, "vendor_user_id": row.vendor_user_id, "input": row.input,
                "rule_version": row.rule_version, "config": config, "checkpoint": row.result or {}}


def finish(student_id, job_id, lease_token, result):
    if not isinstance(result, dict):
        raise ValueError("invalid_assessment_result")
    with session_scope(immediate=True) as session:
        row = session.get(Job, job_id)
        if row is None or row.student_id != student_id or not lease_token or row.lease_token != lease_token:
            return False
        if row.status == "completed":
            return row.result == result
        if row.status not in ("sent", "unknown"):
            return False
        row.status, row.result, row.last_error, row.lease_until = "completed", result, "", None
        return True


def fail(student_id, job_id, lease_token, *, rate_limited=False, retry_after=0):
    if type(retry_after) is not int or not 0 <= retry_after <= 604800:
        raise ValueError("invalid_retry_after")
    with session_scope(immediate=True) as session:
        row = session.get(Job, job_id)
        if (row is None or row.student_id != student_id or row.status != "sent"
                or not lease_token or row.lease_token != lease_token):
            return False
        if not rate_limited:
            row.status, row.last_error, row.lease_until = "unknown", "outcome_unknown", None
            return True
        row.status = "queued" if row.attempts < MAX_ATTEMPTS else "failed"
        row.last_error = "rate_limited"
        row.ready_at = _now() + timedelta(seconds=max(5 * 2 ** row.attempts, retry_after))
        row.lease_token, row.lease_until = "", None
        if row.status == "queued":
            if not _enabled(session, student_id) and not row.input.get("reassessment"):
                row.status = "cancelled"
            elif credentials.read(student_id) is None:
                row.status = "paused"
        return True


def retry_unknown(student_id, job_id):
    with session_scope(immediate=True) as session:
        row = session.get(Job, job_id)
        if row is None or row.student_id != student_id or row.status != "unknown" or not _enabled(session, student_id):
            return False
        row.status, row.last_error = _queue_state(student_id, row.vendor_user_id)
        row.ready_at, row.lease_token, row.lease_until = _now(), "", None
        return True


def status(student_id, job_id, vendor_user_id=None):
    with session_scope() as session:
        row = session.get(Job, job_id)
        if row is None or row.student_id != student_id or (vendor_user_id is not None and row.vendor_user_id != vendor_user_id):
            return None
        result = {key: getattr(row, key) for key in ("id", "source_id", "status", "attempts",
                "credential_version", "used_model", "rule_version", "last_error")}
        result["publication_status"] = (row.result or {}).get("publication_status", "")
        result["publication_error"] = (row.result or {}).get("publication_error", "")
        return result


@contextmanager
def execution_scope(dispatch):
    """仅供已 begin_send 的内部执行者使用，快照不会写回队列或 API。"""
    from deeptutor.multi_user.context import set_current_user, reset_current_user
    from deeptutor.multi_user.models import CurrentUser
    from deeptutor.multi_user.paths import scope_for_user

    user = CurrentUser(id=dispatch["vendor_user_id"], username=dispatch["student_id"], role="student",
                       scope=scope_for_user(dispatch["vendor_user_id"], is_admin=False))
    token = set_current_user(user)
    try:
        with credentials.use_snapshot(dispatch["student_id"], dispatch["config"]):
            yield
    finally:
        reset_current_user(token)


def pending_owners():
    with session_scope() as session:
        return list(session.execute(select(Job.student_id, Job.vendor_user_id).where(
            Job.status.in_(("queued", "claimed", "sent"))).distinct()).all())


def discard(student_id, job_id, lease_token, reason="assessment_unverifiable"):
    with session_scope(immediate=True) as session:
        row = session.get(Job, job_id)
        if (row is None or row.student_id != student_id or row.status != "sent"
                or not lease_token or row.lease_token != lease_token):
            return False
        row.status, row.last_error, row.lease_until = "discarded", reason, None
        return True


def renew(student_id, job_id, lease_token):
    with session_scope(immediate=True) as session:
        row = session.get(Job, job_id)
        if (row is None or row.student_id != student_id or row.status != "sent"
                or not lease_token or row.lease_token != lease_token):
            return False
        row.lease_until = _now() + timedelta(seconds=LEASE_SECONDS)
        return True


def checkpoint_attribution_repair(student_id, job_id, lease_token, error):
    if error not in {"knowledge_point_mismatch", "source_attribution_mismatch"}:
        raise ValueError("invalid_attribution_error")
    with session_scope(immediate=True) as session:
        row = session.get(Job, job_id)
        if (row is None or row.student_id != student_id or row.status != "sent"
                or not lease_token or row.lease_token != lease_token):
            return False
        row.result = {"stage": "attribution_repair", "error": error,
                      "initial_model": row.used_model, "initial_credential_version": row.credential_version}
        return True


def pending_publications():
    with session_scope() as session:
        rows = session.scalars(select(Job).where(Job.status == "completed", Job.ready_at <= _now(),
            Job.result["publication_status"].as_string() == "pending").order_by(Job.created_at, Job.id).limit(50)).all()
        return [(row.student_id, row.vendor_user_id, row.id) for row in rows
                if (row.result or {}).get("publication_status") == "pending"]


def publication(student_id, job_id):
    with session_scope() as session:
        row = session.get(Job, job_id)
        if (row is None or row.student_id != student_id or row.status != "completed"
                or (row.result or {}).get("publication_status") != "pending"):
            return None
        return {"id": row.id, "student_id": row.student_id, "vendor_user_id": row.vendor_user_id,
                "input": row.input, "result": row.result, "rule_version": row.rule_version,
                "used_model": row.used_model, "credential_version": row.credential_version}


def publication_failed(student_id, job_id, *, blocked=False):
    with session_scope(immediate=True) as session:
        row = session.get(Job, job_id)
        if row is None or row.student_id != student_id or (row.result or {}).get("publication_status") != "pending":
            return
        attempts = row.result.get("publication_attempts", 0) + 1
        row.result = {**row.result, "publication_status": "blocked" if blocked else "pending",
                      "publication_error": "publication_input_invalid" if blocked else "publication_retry_pending",
                      "publication_attempts": attempts}
        row.ready_at = _now() + timedelta(seconds=min(300, 5 * 2 ** min(attempts, 6)))


def sync_publication(student_id, job_id, receipt):
    from database.repository import Repository

    with session_scope(immediate=True) as session:
        row = session.get(Job, job_id)
        if row is None or row.student_id != student_id or row.status != "completed":
            return False
        if (row.result or {}).get("publication_status") == "published":
            return True
        if (row.result or {}).get("publication_status") != "pending":
            return False
        if receipt["job_id"] != job_id or receipt["knowledge_point_id"] != row.result["judgment"]["knowledge_point_id"]:
            raise ValueError("publication_receipt_mismatch")
        repo = Repository()
        repo.ensure_student(student_id)
        session.flush()  # 新账号须先写入，当前 ORM 未配置学生到事件的依赖关系。
        event = repo.record_event(student_id, "vendor-assessment:" + job_id, receipt["knowledge_point_id"],
                                  "vendor_assessment", receipt, status="synced")
        evidence_id = repo.add_event_evidence(event["id"], receipt["knowledge_point_id"], "vendor_assessment",
            json.dumps(receipt, ensure_ascii=False), 1.0, "vendor-result",
            verification="vendor_recorded", independent=False,
            source_quote=row.result["judgment"]["answer_excerpt"])
        from integrations.deeptutor.student_memory import record_assessment_memory
        record_assessment_memory(session, row, receipt, event["id"])
        reassessment = row.input.get("reassessment")
        if reassessment:
            original = session.get(Job, reassessment["original_job_id"])
            if (original is None or original.student_id != student_id or original.vendor_user_id != row.vendor_user_id
                    or receipt["assessment"]["visual_context"].get("supersedes_evidence_id") != original.result.get("vendor_evidence_id")):
                raise ValueError("reassessment_publication_mismatch")
            original.result = {**original.result, "effective_reassessment_id": row.id}
        row.result = {**row.result, "publication_status": "published", "publication_error": "",
                      "vendor_evidence_id": receipt["vendor_evidence_id"], "evidence_id": evidence_id}
        return True


def source_info(student_id,vendor_user_id,snapshot):
    from deeptutor.multi_user.context import get_current_user_or_none
    from deeptutor.services.workspace.context import workspace_context
    from deeptutor.services.session import get_sqlite_session_store
    from urllib.parse import quote
    user=get_current_user_or_none()
    if not user or (user.username,user.id)!=(student_id,vendor_user_id):return {"source_status":"unavailable"}
    try:
        session_id=snapshot.get("session_id","");workspace=snapshot.get("workspace_id","")
        with workspace_context(workspace):
            store=get_sqlite_session_store()
            if not store.db_path.is_file() or store._get_session_sync(session_id) is None:return {"source_status":"deleted"}
        return {"source_status":"available","source_url":"/chat/"+quote(session_id,safe="")+("?dt_workspace="+quote(workspace,safe="") if workspace else "")}
    except Exception:
        return {"source_status":"unavailable"}


def recent_jobs(student_id, vendor_user_id):
    with session_scope() as session:
        rows = session.scalars(select(Job).where(Job.student_id == student_id, Job.vendor_user_id == vendor_user_id, REASSESSMENT_ROOT.is_(None))
                               .order_by(Job.created_at.desc(), Job.id.desc()).limit(20)).all()
        # 每个原评分只取当前应展示的复评，避免载入全部失败重试历史。
        ranked_reviews = select(Job.id, func.row_number().over(partition_by=REASSESSMENT_ROOT,
            order_by=(case((Job.status == "completed", 0), (Job.status.in_(("queued", "claimed", "paused", "sent", "unknown")), 1), else_=2),
                      Job.created_at.desc(), Job.id.desc())).label("position")).where(
                Job.student_id == student_id, Job.vendor_user_id == vendor_user_id,
                REASSESSMENT_ROOT.in_([row.id for row in rows])).subquery()
        reviews = session.scalars(select(Job).join(ranked_reviews, Job.id == ranked_reviews.c.id)
            .where(ranked_reviews.c.position == 1)).all() if rows else []
        items = []
        for row in rows:
            saved = row.result or {}
            judgment = saved.get("judgment", {}) if row.status == "completed" else {}
            kp_id = judgment.get("knowledge_point_id", "")
            snapshot = row.input or {}
            targets = snapshot.get("targets", [])
            point = next((point for point in targets if point["id"] == kp_id), None)
            assistance = snapshot.get("assistance", {}).get(kp_id, {})
            sources = {source["id"]: source for source in snapshot.get("sources", [])}
            related = [item for item in reviews if item.input["reassessment"]["original_job_id"] == row.id]
            review = next((item for item in related if item.status == "completed"), None)
            if review is None:
                review = next((item for item in related if item.status in {"queued", "claimed", "paused", "sent", "unknown"}), related[0] if related else None)
            review_result = (review.result or {}) if review else {}
            review_judgment = review_result.get("judgment", {}) if review and review.status == "completed" else {}
            items.append({"id": row.id, "status": row.status, **source_info(student_id,vendor_user_id,snapshot),
                "reassessment": {"id": review.id, "status": review.status,
                    "publication_status": review_result.get("publication_status", ""),
                    "pause_reason": review.last_error if review.status == "paused" else "",
                    "pause_message": capabilities.MESSAGES.get(review.last_error, "请先验证当前配置的评估能力。") if review.status == "paused" else "",
                    "passed": review_judgment.get("passed"), "feedback": review_judgment.get("feedback", ""),
                    "reason": review.input["reassessment"]["reason"],
                    "effective": saved.get("effective_reassessment_id") == review.id,
                    "can_retry": review.status in {"failed", "discarded", "cancelled", "unknown"}} if review else None,
                "pause_reason": row.last_error if row.status == "paused" else "",
                "pause_message": capabilities.MESSAGES.get(row.last_error, "请先验证当前配置的评估能力。") if row.status == "paused" else "",
                "created_at": row.created_at.isoformat() + "Z",
                "knowledge_point": point["name"] if point else "、".join(point["name"] for point in targets),
                "passed": judgment.get("passed"), "feedback": judgment.get("feedback", ""),
                "answer": snapshot.get("answer", "") if judgment else "",
                "publication_status": saved.get("publication_status", ""),
                "assistance_status": "assisted" if assistance.get("status") == "assisted" else "not_verified",
                "independent": False,
                "citations": [{"quote": cite["quote"], "document_id": sources[cite["source_id"]]["document_id"],
                    "version": sources[cite["source_id"]]["version"]} for cite in judgment.get("citations", [])
                    if cite["source_id"] in sources]})
        return {"jobs": items}


def request_reassessment(student_id, vendor_user_id, job_id, request_id, reason, *, confirm_cost, confirm_unknown_retry=False):
    from copy import deepcopy
    from uuid import UUID
    from integrations.deeptutor.assessment_intake import RULE_VERSION, confirmed_catalog

    if confirm_cost is not True or type(confirm_unknown_retry) is not bool:
        raise ValueError("reassessment_cost_confirmation_required")
    try:
        request_id = str(UUID(request_id))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("invalid_reassessment_request_id") from None
    if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 1000:
        raise ValueError("invalid_reassessment_reason")
    reason = reason.strip()
    with session_scope(immediate=True) as session:
        original = session.get(Job, job_id)
        if original is None or original.student_id != student_id or original.vendor_user_id != vendor_user_id:
            raise ValueError("assessment_not_found")
        if original.input.get("reassessment"):
            raise ValueError("reassessment_requires_original")
        source_id = f"reassessment:{job_id}:{request_id}"
        existing = session.scalar(select(Job).where(Job.student_id == student_id, Job.source_id == source_id))
        if existing:
            if existing.input["reassessment"]["reason"] != reason:
                raise ValueError("reassessment_request_conflict")
            return {"id": existing.id, "status": existing.status, "already_submitted": True}
        if original.status != "completed" or (original.result or {}).get("publication_status") != "published":
            raise ValueError("assessment_not_published")
        if original.result.get("independent") is not False:
            raise ValueError("reassessment_qualification_unsupported")
        children = session.scalars(select(Job).where(Job.student_id == student_id, REASSESSMENT_ROOT == job_id)).all()
        if any(row.status == "completed" for row in children):
            raise ValueError("reassessment_already_succeeded")
        active = next((row for row in children if row.status in {"queued", "claimed", "paused", "sent"}), None)
        if active:
            return {"id": active.id, "status": active.status, "already_submitted": True}
        unknown = [row for row in children if row.status == "unknown"]
        if unknown and confirm_unknown_retry is not True:
            raise ValueError("reassessment_outcome_unknown")
        catalog, version = confirmed_catalog()
        snapshot = deepcopy(original.input)
        previous = original.result["judgment"]
        kp_id = previous["knowledge_point_id"]
        if original.rule_version != RULE_VERSION or version != snapshot.get("catalog_version") or kp_id not in catalog:
            raise ValueError("reassessment_catalog_changed")
        snapshot["targets"] = [point for point in snapshot["targets"] if point["id"] == kp_id]
        if not snapshot["targets"] or not original.result.get("vendor_evidence_id"):
            raise ValueError("assessment_source_incomplete")
        snapshot["reassessment"] = {"original_job_id": job_id, "request_id": request_id, "reason": reason,
            "previous_judgment": {key: previous[key] for key in ("knowledge_point_id", "passed", "feedback")},
            "supersedes_evidence_id": original.result["vendor_evidence_id"]}
        encoded = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, allow_nan=False)
        if len(encoded.encode("utf-8")) > 65536:
            raise ValueError("reassessment_input_too_large")
        for row in unknown:
            row.status, row.lease_token, row.lease_until = "superseded", "", None
        ident = str(uuid4())
        status, error = _queue_state(student_id, vendor_user_id)
        session.add(Job(id=ident, student_id=student_id, vendor_user_id=vendor_user_id, source_id=source_id,
            input=snapshot, input_hash=sha256(encoded.encode("utf-8")).hexdigest(), rule_version=RULE_VERSION,
            status=status, last_error=error))
        return {"id": ident, "status": status, "already_submitted": False}


def pause_rejected(student_id, job_id, token, error):
    if error not in capabilities.MESSAGES: raise ValueError("invalid_assessment_error")
    with session_scope(immediate=True) as session:
        row = session.get(Job, job_id)
        if row is None or row.student_id != student_id or row.status != "sent" or row.lease_token != token:
            return False
        row.status, row.last_error, row.lease_token, row.lease_until = "paused", error, "", None
        return True
