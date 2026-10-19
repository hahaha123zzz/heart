"""用宿主已保存任务构造教材指针；恢复正文始终重新检查宿主事实。"""
from __future__ import annotations

import hashlib
import json
import os

from database.learning_tasks import LearningTaskRepository, TaskConflict, now
from database.database import session_scope
from database.models import ConversationRow, Student
from database.repository import Repository
from knowledge.course_config import COURSE_ID, COURSE_TITLE

from .client import BackendUnavailable, DeepTutorBackend
from .turn_contract import SourcePointer, TurnProjection


def checked_task(student_id, session_id, task_id, revision, *, allow_active=False):
    row = LearningTaskRepository().get(student_id, session_id, task_id)
    if row["revision"] != revision:
        raise TaskConflict("task_conflict", "任务版本已变化，请恢复最新任务")
    if row["status"] in ("cancelled", "expired") or row["expires_at"] <= now():
        raise TaskConflict("task_expired", "任务已取消或过期，旧回答不能恢复")
    if Repository().memory_epoch(student_id, row["knowledge_point"]) != row["epoch"]:
        raise TaskConflict("memory_deleted", "相关记忆已删除，旧回答不能恢复")
    with session_scope() as db:
        student = db.get(Student, student_id)
        if student is None or (student.expires_at is not None and student.expires_at <= now()):
            raise TaskConflict("account_missing", "学生账户已删除或过期")
        cid = row["result"].get("conversation_id")
        if cid is not None:
            conversation = db.get(ConversationRow, cid)
            if conversation is None or conversation.student_id != student_id:
                raise TaskConflict("memory_deleted", "原对话已删除，旧回答不能恢复")
    if not allow_active and row["status"] in ("ready", "executing"):
        raise TaskConflict("task_busy", "任务正在处理，请稍后恢复")
    return row


def source_pointers(payload, result, document_versions=None):
    from knowledge.pdf_reader import document, document_for_chapter, documents, pdf_path
    from knowledge.course import get_section

    sources = []
    checked = {}
    if document_versions:
        published = {record["document_id"]: record["version"] for record in documents()}
        if any(published.get(key) != version for key, version in document_versions.items()):
            raise ValueError("发布教材版本已变化")

    def record_for(document_id, version):
        record = document(document_id)
        if record is None or record["version"] != version:
            raise ValueError("教材版本已变化")
        if document_id not in checked:
            if hashlib.sha256(pdf_path(record).read_bytes()).hexdigest() != version:
                raise ValueError("教材文件已变化")
            checked[document_id] = record
        return record

    selection = payload.get("selection")
    if selection:
        record = record_for(selection["document_id"], selection["version"])
        sources.append(SourcePointer(kind="selection", document_id=record["document_id"],
            version=record["version"], chapter_id=record["chapter_id"], rects=selection["rects"]))
    location = payload.get("reader_location")
    if location:
        record = document_for_chapter(location["chapter_id"])
        if record is None or get_section(location["chapter_id"], location["section_id"]) is None:
            raise ValueError("教材小节不存在")
        historical = (document_versions or {}).get(record["document_id"])
        if historical is None:
            raise ValueError("历史任务没有教材版本快照")
        record_for(record["document_id"], historical)
        sources.append(SourcePointer(kind="section", document_id=record["document_id"],
            version=record["version"], **location))
    for reference in result.get("pdf_references", []):
        evidence = reference.get("evidence") or {}
        locator = reference.get("selection_ref") or {}
        doc_id = evidence.get("document_id") or locator.get("document_id")
        version = evidence.get("document_version") or locator.get("version")
        record = record_for(doc_id, version)
        sources.append(SourcePointer(kind="citation", document_id=doc_id, version=version,
            chapter_id=record["chapter_id"], section_id=evidence.get("section_id") or locator.get("section_id"),
            evidence_id=evidence.get("evidence_id") or locator.get("evidence_id")))
    return sources


def projection_for(row):
    digest = hashlib.sha256(json.dumps(row["result"], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return TurnProjection(student_id=row["student_id"], session_id=row["session_id"],
        course_id=COURSE_ID, course_title=COURSE_TITLE, task_id=row["id"], task_revision=row["revision"],
        outcome=row["status"], result_digest=digest, sources=source_pointers(row["payload"], row["result"], row.get("context", {}).get("document_versions")))


def sync_saved_turn(request, result):
    if os.getenv("DEEPTUTOR_TURN_SYNC", "0") != "1" or not result.get("task_id") or not result.get("task_revision"):
        return result
    try:
        row = checked_task(request.student_id, request.session_id, result["task_id"], result["task_revision"])
        state = {"status": "ready", **DeepTutorBackend().publish_turn(projection_for(row).model_dump())}
    except (TaskConflict, BackendUnavailable, ValueError, OSError):
        state = {"status": "unavailable"}
    return {**result, "deeptutor_turn": state}


def replay_events(student_id, session_id, task_id, revision, after_seq):
    row = checked_task(student_id, session_id, task_id, revision)
    try:
        projection = projection_for(row)
    except (ValueError, OSError) as exc:
        raise TaskConflict("source_changed", "教材来源已变化，请重新提问") from exc
    # 恢复时补传可覆盖首次同步失败、断网以及保存后进程中断。
    backend = DeepTutorBackend()
    backend.publish_turn(projection.model_dump())
    cursor = projection.model_dump(include={"student_id", "session_id", "course_id", "course_title", "task_id", "task_revision"})
    result = backend.turn_events({**cursor, "after_seq": after_seq})
    # 网络等待期间可能发生删除、取消或澄清推进。
    checked_task(student_id, session_id, task_id, revision)
    expected_sources = {"sources": [source.model_dump() for source in projection.sources]}
    expected_done = {"host_task_id": task_id, "host_task_revision": revision,
                     "outcome": row["status"], "result_digest": projection.result_digest}
    canonical = {1: ("sources", expected_sources), 2: ("done", expected_done)}
    expected_seqs = [seq for seq in (1, 2) if seq > after_seq]
    events = result["events"]
    if (len(events) != len(expected_seqs)
            or [event.get("seq") for event in events if isinstance(event, dict)] != expected_seqs):
        raise BackendUnavailable("DeepTutor 回合事件序号无效")
    output = []
    for event in events:
        kind, metadata = canonical[event["seq"]]
        if event.get("type") != kind or event.get("metadata") != metadata or event.get("content"):
            raise BackendUnavailable("DeepTutor 回合事件内容无效")
        data = expected_sources if kind == "sources" else row["result"]
        output.append({"id": f"{task_id}:{revision}:{event['seq']}", "event": kind, "data": data})
    return output
