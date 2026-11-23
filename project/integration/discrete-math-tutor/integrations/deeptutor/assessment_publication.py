"""将已保存评分幂等发布到厂家，再同步 H；此流程不调用模型。"""
from __future__ import annotations

import asyncio
import json
import uuid

from integrations.deeptutor import assessment_jobs as jobs


def publish_to_path(dispatch):
    from deeptutor.learning.policy import find_knowledge_point, is_assessed_mastered, learning_stage
    from deeptutor.learning.service import LearningService
    from deeptutor.learning.storage import LearningStore
    from integrations.deeptutor.assessment_worker import validate_judgment

    snapshot, result = dispatch["input"], dispatch["result"]
    judgment = validate_judgment(json.dumps(result["judgment"], ensure_ascii=False), snapshot)
    if judgment is None or result["catalog_version"] != snapshot["catalog_version"]:
        raise ValueError("publication_result_invalid")
    kp_id = judgment["knowledge_point_id"]
    assistance = snapshot.get("assistance", {}).get(kp_id, {})
    status = "assisted" if assistance.get("status") == "assisted" else "not_verified"
    # shortcut: 事件追踪尚未覆盖全部提示/看答案入口，不据记录缺失放行独立证据。
    audit = {"independent": False, "assistance_status": status, "assistance": assistance, "job_id": dispatch["id"],
             "judgment": judgment, "answer": snapshot["answer"], "sources": snapshot["sources"],
             "catalog_version": snapshot["catalog_version"], "rule_version": dispatch["rule_version"],
             "model": dispatch["used_model"], "credential_version": dispatch["credential_version"],
             "initial_model": result["initial_model"],
             "initial_credential_version": result["initial_credential_version"],
             "source_turn_id": snapshot["turn_id"], "message_id": snapshot["message_id"]}
    audit.update({key:snapshot[key] for key in ("mapping_version", "graph_release_id") if snapshot.get(key)})
    if snapshot.get("reassessment"):
        audit["reassessment"] = snapshot["reassessment"]
        audit["supersedes_evidence_id"] = snapshot["reassessment"]["supersedes_evidence_id"]
    turn_id = "heart-assessment:" + dispatch["id"]
    evidence_id = uuid.uuid5(uuid.NAMESPACE_URL,
        f"deeptutor:qualitative:{snapshot['session_id']}:{turn_id}:{kp_id}").hex
    service = LearningService(LearningStore())
    progress = service.record_qualitative_for_path(snapshot["mastery_path_id"], kp_id,
        passed=judgment["passed"], evidence=judgment["feedback"], session_id=snapshot["session_id"],
        turn_id=turn_id, assessment_context=audit)
    evidence = next((item for item in progress.learning_evidence if item.evidence_id == evidence_id), None)
    if evidence is None or evidence.visual_context.get("job_id") != dispatch["id"]:
        raise ValueError("publication_identity_conflict")
    kp, _, _ = find_knowledge_point(progress, kp_id)
    state = progress.repetition_states.get(kp_id)
    return {"job_id": dispatch["id"], "student_id": dispatch["student_id"],
            "vendor_user_id": dispatch["vendor_user_id"],
            "knowledge_point_id": kp_id, "vendor_evidence_id": evidence_id,
            "workspace_id": snapshot.get("workspace_id", ""), "mastery_path_id": snapshot["mastery_path_id"],
            "path_version": progress.version, "assessed_mastered": is_assessed_mastered(progress, kp),
            "qualitative_mastery": progress.qualitative_mastery.get(kp_id),
            "learning_stage": learning_stage(progress, kp_id),
            "retention": state.model_dump(mode="json") if state else None,
            "assessment": evidence.model_dump(mode="json")}


async def publish_one(student_id, job_id):
    from deeptutor.api.routers.auth import get_user_info
    from deeptutor.multi_user.models import CurrentUser
    from deeptutor.multi_user.paths import scope_for_user, user_context
    from deeptutor.services.workspace.context import workspace_context
    from deeptutor.learning.assessment import AssessmentRecord, record_assessment

    dispatch = await asyncio.to_thread(jobs.publication, student_id, job_id)
    if dispatch is None:
        return False
    account = await asyncio.to_thread(get_user_info, student_id)
    if (not account or account.get("id") != dispatch["vendor_user_id"]
            or account.get("disabled") or account.get("role") == "admin"):
        return False
    user = CurrentUser(id=dispatch["vendor_user_id"], username=student_id, role="student",
                       scope=scope_for_user(dispatch["vendor_user_id"], is_admin=False))
    try:
        with user_context(user), workspace_context(dispatch["input"].get("workspace_id", "")):
            receipt = await asyncio.to_thread(publish_to_path, dispatch)
            evidence = receipt["assessment"]
            audit = evidence["visual_context"]
            outcome = await record_assessment(AssessmentRecord(
                session_id=evidence["session_id"], turn_id=evidence["turn_id"],
                question_id="heart:" + job_id, source="mastery_path", assessment_type="qualitative",
                question="聊天作答评估：" + receipt["knowledge_point_id"],
                result=evidence["result"], user_answer=audit["answer"],
                explanation=audit["judgment"]["feedback"],
                mastery_path_id=receipt["mastery_path_id"], knowledge_point_id=receipt["knowledge_point_id"],
                hints_used=evidence["hints_used"], visual_context=audit,
                attempt_id=receipt["vendor_evidence_id"], created_at=evidence["timestamp"],
                updated_at=evidence["timestamp"]))
            receipt["vendor_attempt_id"] = outcome.attempt_id
        return await asyncio.to_thread(jobs.sync_publication, student_id, job_id, receipt)
    except (ValueError, KeyError):
        await asyncio.to_thread(jobs.publication_failed, student_id, job_id, blocked=True)
    except Exception:
        await asyncio.to_thread(jobs.publication_failed, student_id, job_id)
    return False
