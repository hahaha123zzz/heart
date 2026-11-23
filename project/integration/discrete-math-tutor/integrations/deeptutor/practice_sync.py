"""把厂家复习提交后的持久待同步记录投递到 H。"""
from __future__ import annotations

import asyncio
import json
import logging

from database.database import session_scope
from integrations.deeptutor.assessment_intake import confirmed_catalog

log = logging.getLogger(__name__)


def capture(conn, entry, outcome, answer, reviewed_at):
    from deeptutor.multi_user.context import get_current_user_or_none
    from deeptutor.services.workspace.context import current_workspace_id

    user = get_current_user_or_none()
    point_id = entry["knowledge_point_id"]
    if user is None or user.is_admin or not point_id or not entry["mastery_path_id"]:
        return None
    catalog, version = confirmed_catalog()
    if point_id not in catalog:
        return None
    # 题目记录可编辑，必须与同一条厂家不可变评分的题干、选项和答案一致。
    attempt = conn.execute("""SELECT attempt_id, assessment_json FROM assessment_attempts
        WHERE notebook_entry_id = ? AND mastery_path_id = ? AND knowledge_point_id = ?
          AND source = ? AND result IN ('correct', 'incorrect', 'partial')
        ORDER BY occurred_at DESC, attempt_id DESC LIMIT 1""",
        (entry["id"], entry["mastery_path_id"], point_id, entry["source"])).fetchone()
    if attempt is None:
        return None
    original = json.loads(attempt["assessment_json"])
    if (any(original.get(key, "") != entry[key] for key in ("question", "correct_answer", "question_type"))
            or original.get("options", {}) != json.loads(entry["options_json"] or "{}")):
        return None
    return {"student_id": user.username, "vendor_user_id": user.id, "workspace_id": current_workspace_id(),
            "catalog_version": version, "knowledge_point_id": point_id, "source_attempt_id": attempt["attempt_id"],
            "mastery_path_id": entry["mastery_path_id"], "reviewed_at": reviewed_at, "answer": answer,
            "review": {key: outcome[key] for key in ("correct", "self_report", "rating", "due_at", "review_count", "assistance")}}


def sync(event_id, payload):
    from database.repository import Repository

    student_id = payload["student_id"]
    point = payload["knowledge_point_id"]
    catalog, version = confirmed_catalog()
    if not catalog:
        raise RuntimeError("Practice catalog unavailable")
    if point not in catalog or payload["catalog_version"] != version:
        return "catalog_changed"
    with session_scope(immediate=True) as session:
        repo = Repository()
        repo.ensure_student(student_id)
        session.flush()
        event = repo.record_event(student_id, "vendor-practice:" + event_id, point,
                                  "vendor_practice_review", payload, status="synced")
        repo.add_event_evidence(event["id"], point, "vendor_practice_review",
            json.dumps(payload, ensure_ascii=False), 1.0, "vendor-review", verification="vendor_recorded",
            independent=False, source_quote=payload["answer"])
    return "synced"


def drain_store(store, student_id, vendor_id, workspace_id):
    if not store.db_path.is_file():
        return
    with store.connect() as conn:
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'practice_review_outbox'").fetchone()
        if not exists:
            return
        rows = conn.execute("SELECT * FROM practice_review_outbox ORDER BY rowid LIMIT 25").fetchall()
    for row in rows:
        payload = json.loads(row["payload_json"])
        if (payload.get("student_id"), payload.get("vendor_user_id"), payload.get("workspace_id")) != (student_id, vendor_id, workspace_id):
            continue
        status = sync(row["event_id"], payload)
        with store.connect() as conn:
            conn.execute("UPDATE practice_review_events SET outcome_json = json_set(outcome_json, '$.learning_sync', ?) WHERE request_id = ?",
                         (status, row["request_id"]))
            conn.execute("DELETE FROM practice_review_outbox WHERE event_id = ?", (row["event_id"],))


def sync_pending():
    from deeptutor.services.auth import list_users
    from deeptutor.multi_user.models import CurrentUser
    from deeptutor.multi_user.paths import scope_for_user, user_context
    from deeptutor.services.path_service import get_path_service
    from deeptutor.services.practice.storage import PracticeStore
    from deeptutor.services.workspace import get_content_workspace_service
    from deeptutor.services.workspace.context import workspace_context

    for account in list_users():
        if account.get("disabled") or account.get("role") == "admin" or not account.get("id"):
            continue
        student, vendor_id = account["username"], account["id"]
        user = CurrentUser(id=vendor_id, username=student, role="student", scope=scope_for_user(vendor_id, is_admin=False))
        with user_context(user):
            try:
                default = PracticeStore(get_path_service().get_chat_history_db())
                drain_store(default, student, vendor_id, "")
                from integrations.deeptutor.assessment_delivery import drain_store as drain_assessments
                from deeptutor.services.session.sqlite_store import SQLiteSessionStore
                drain_assessments(SQLiteSessionStore(default.db_path),student,vendor_id,"")
                workspaces = get_content_workspace_service().list_workspaces()
            except Exception:
                log.warning("Practice sync will retry after a storage error")
                continue
            for row in workspaces:
                if row["kind"] != "workspace":
                    continue
                try:
                    with workspace_context(row["workspace_id"]):
                        path=get_path_service().get_chat_history_db()
                        drain_store(PracticeStore(path), student, vendor_id, row["workspace_id"])
                        drain_assessments(SQLiteSessionStore(path),student,vendor_id,row["workspace_id"])
                except Exception:
                    log.warning("Workspace practice sync will retry after a storage error")


async def run_loop():
    while True:
        try:
            await asyncio.to_thread(sync_pending)
        except Exception:
            log.warning("Practice sync scan failed and will retry")
        await asyncio.sleep(15)
