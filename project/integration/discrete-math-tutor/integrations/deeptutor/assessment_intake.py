"""仅从已完成回合、已确认目录和厂家当前路径收集定性评估候选。"""
from __future__ import annotations

import asyncio
from hashlib import sha256
import json
import logging
from pathlib import Path

from integrations.deeptutor import assessment_jobs as jobs

from knowledge.course_config import PSYCHOLOGY_DIR

REGISTRY = PSYCHOLOGY_DIR / "kc_registry_full.json"
RULE_VERSION = "vendor-qualitative-grounded-v1"


def confirmed_catalog():
    try:
        raw = REGISTRY.read_bytes()
        value = json.loads(raw)
    except (OSError, ValueError):
        return {}, ""
    if not isinstance(value, dict):
        return {}, ""
    if value.get("course_id") != "experimental-psychology-3" or value.get("status") != "confirmed":
        return {}, ""
    points = {item["id"]: item for item in value.get("knowledge_components", [])
              if item.get("status") == "confirmed" and item.get("id")}
    return points, sha256(raw).hexdigest()



def assistance_for_turn(store, path_id, execution, answer, targets, *, message_id=None, catalog_version=""):
    """只用厂家持久事件证明已有辅助；记录缺失不推断独立。"""
    states = {kp_id: {"status": "not_verified", "coverage": "partial", "events": []} for kp_id in targets}
    events = store.list_events(path_id)
    if type(message_id) is int and message_id > 0 and catalog_version:
        for kp_id in states:
            references = [event for event in events
                if event.event_type in {"chat.reference_provided", "chat.teaching_provided"}
                and event.session_id == execution.session_id
                and event.turn_id != execution.turn_id and event.payload.get("catalog_version") == catalog_version
                and type(event.payload.get("assistant_message_id")) is int
                and 0 < event.payload["assistant_message_id"] < message_id
                and kp_id in event.payload.get("knowledge_point_ids", [])]
            if references:
                # 仅保留最近一次已提供参考；编号证明回复持久化早于本次作答。
                reference = max(references, key=lambda event: event.payload["assistant_message_id"])
                states[kp_id] = {"status": "assisted", "coverage": "partial", "rule_version": "chat-assistance-order-v2",
                    "reason": "teaching_provided" if reference.event_type == "chat.teaching_provided" else "textbook_reference_provided", "events": [{"id": reference.id,
                    "revision": reference.revision, "type": reference.event_type,
                    "assistant_message_id": reference.payload["assistant_message_id"],
                    "sources": reference.payload.get("sources", []),
                    "source_event_ids": reference.payload.get("source_event_ids", [])}]}
    for submitted in reversed(events):
        if (submitted.event_type != "interaction.answered" or submitted.session_id != execution.session_id
                or submitted.turn_id != execution.turn_id):
            continue
        question_id = submitted.payload.get("interaction_id", "")
        interaction = store.get_interaction(path_id, question_id)
        if interaction is None or interaction.user_answer.strip() != answer:
            continue
        kp_id = interaction.question.knowledge_point_id
        if kp_id not in states or states[kp_id].get("question_id"):
            continue
        registered = next((event for event in reversed(events) if event.id < submitted.id
            and event.event_type == "interaction.registered" and event.payload.get("interaction_id") == question_id), None)
        if registered is None:
            continue
        teaching = [event for event in events if registered.id < event.id < submitted.id
            and event.event_type == "objective.explained" and event.payload.get("knowledge_point_id") == kp_id]
        prior = states[kp_id]
        ordered = [registered, *teaching, submitted]
        states[kp_id] = {"status": "assisted" if teaching or prior["status"] == "assisted" else "not_verified", "coverage": "partial",
            "question_id": question_id, "rule_version": "server-event-order-v1",
            "events": sorted([*prior["events"], *[{"id": event.id, "revision": event.revision, "type": event.event_type} for event in ordered]], key=lambda item: item["id"])}
    return states

def build_snapshot(execution, context, events, user_message_id):
    from deeptutor.services.workspace.context import current_workspace_id
    from deeptutor.learning.storage import LearningStore
    from deeptutor.multi_user.context import get_current_user_or_none

    user = get_current_user_or_none()
    if user is None or user.is_admin or not context or not user_message_id:
        return None
    from integrations.deeptutor.screenshot_intake import receipt_for
    screenshot = receipt_for(context, user, execution) if context.attachments else None
    if context.attachments and screenshot is None:
        return None
    answer = str(execution.payload.get("content") or "").strip()
    if screenshot and screenshot.reading.student_answer.strip():
        answer += "\n【截图中识别的学生作答】\n" + screenshot.reading.student_answer.strip()
    if not answer or len(answer) > 8000:
        return None
    catalog, version = confirmed_catalog()
    if not catalog:
        return None
    path_id = str(context.metadata.get("mastery_path_id") or "")
    if not path_id:
        return None
    learning_store = LearningStore()
    progress = learning_store.load(path_id)
    if progress is None:
        return None
    points = {point.id: point for module in progress.modules for point in module.knowledge_points
              if point.id in catalog and point.type.value in {"concept", "design"}}
    sources, targets = {}, {}
    for event in events:
        for source in (event.get("metadata") or {}).get("sources", []):
            if source.get("type") != "heart_textbook_evidence":
                continue
            evidence = (source.get("location") or {}).get("evidence") or {}
            quote = str(source.get("quote") or "")
            if (not quote or quote not in str(source.get("text") or "") or not source.get("version")
                    or evidence.get("document_version") != source["version"]
                    or evidence.get("evidence_id") != source.get("source_id")):
                continue
            for kp_id, point in points.items():
                canonical = catalog[kp_id]
                if (source.get("chapter_id"), source.get("section_id")) != (canonical.get("chapter_id"), canonical.get("section_id")):
                    continue
                source_id = source["source_id"]
                sources[source_id] = {"id": source_id, "text": quote, "document_id": source["document_id"],
                                      "version": source["version"]}
                target = targets.setdefault(kp_id, {"id": kp_id, "name": canonical["name"],
                                                    "type": point.type.value, "source_ids": []})
                if source_id not in target["source_ids"]:
                    target["source_ids"].append(source_id)
    if not targets or len(targets) > 5:
        return None
    history = [{"role": item.get("role"), "content": item.get("content")}
               for item in context.conversation_history[-4:] if isinstance(item.get("content"), str)]
    snapshot = {"session_id": execution.session_id, "turn_id": execution.turn_id,
                "message_id": str(user_message_id), "workspace_id": current_workspace_id(),
                "answer": answer, "history": history,
                "targets": list(targets.values()), "sources": list(sources.values()),
                "catalog_version": version, "mastery_path_id": path_id,
                "independent": False, "assistance_status": "not_verified",
                "assistance": assistance_for_turn(learning_store, path_id, execution, answer, targets,
                    message_id=user_message_id, catalog_version=version)}
    from integrations.deeptutor.student_memory import control_for_turn
    snapshot["memory_control"] = control_for_turn(context, user, execution)
    from knowledge.student_graph import assessment_versions
    snapshot.update(assessment_versions(version))
    if screenshot:
        snapshot["screenshot"] = screenshot.audit()
        if screenshot.reading.assisted:
            snapshot["assistance_status"] = "assisted"
            for state in snapshot["assistance"].values():
                state.update(status="assisted", reason="screenshot_contains_answer_or_steps",
                    screenshot_input_hash=screenshot.input_hash, rule_version="screenshot-assistance-v1")
    if len(json.dumps(snapshot, ensure_ascii=False).encode("utf-8")) > 60000:
        return None
    return user.username, user.id, f"{execution.session_id}:{user_message_id}", snapshot


def record_displayed_references(snapshot, context, events):
    from deeptutor.learning.storage import LearningStore
    assistant_id = context.metadata.get("persisted_assistant_message_id")
    if type(assistant_id) is not int or assistant_id <= 0:
        return
    displayed = {source.get("source_id") for event in events if event.get("type") == "sources"
                 for source in (event.get("metadata") or {}).get("sources", [])}
    sources = [source for source in snapshot["sources"] if source["id"] in displayed]
    points = [point["id"] for point in snapshot["targets"] if displayed.intersection(point["source_ids"])]
    if not sources or not points:
        return
    LearningStore().record_chat_assistance(snapshot["mastery_path_id"], session_id=snapshot["session_id"],
        turn_id=snapshot["turn_id"], payload={"assistant_message_id": assistant_id,
            "catalog_version": snapshot["catalog_version"], "knowledge_point_ids": points,
            "sources": [{"id": source["id"], "version": source["version"]} for source in sources]})


def record_completed_teaching(execution, context):
    from deeptutor.learning.storage import LearningStore
    from deeptutor.multi_user.context import get_current_user_or_none
    user = get_current_user_or_none()
    if user is None or user.is_admin or not context:
        return
    assistant_id = context.metadata.get("persisted_assistant_message_id")
    path_id = str(context.metadata.get("mastery_path_id") or "")
    if (not path_id or type(assistant_id) is not int or assistant_id <= 0
            or context.metadata.get("persisted_assistant_has_content") is not True):
        return
    catalog, version = confirmed_catalog()
    if not catalog:
        return
    store = LearningStore()
    progress = store.load(path_id)
    if progress is None:
        return
    valid = {point.id for module in progress.modules for point in module.knowledge_points if point.id in catalog}
    teaching = [event for event in store.list_events(path_id) if event.event_type == "objective.explained"
        and event.session_id == execution.session_id and event.turn_id == execution.turn_id
        and event.payload.get("knowledge_point_id") in valid]
    if teaching:
        store.record_chat_assistance(path_id, session_id=execution.session_id, turn_id=execution.turn_id,
            event_type="chat.teaching_provided", payload={"assistant_message_id": assistant_id,
                "catalog_version": version, "source_event_ids": [event.id for event in teaching],
                "knowledge_point_ids": sorted({event.payload["knowledge_point_id"] for event in teaching})})


async def completed_turn(execution, context, events, user_message_id):
    from integrations.deeptutor.student_memory import record_chat_difficulty
    try:
        await asyncio.to_thread(record_chat_difficulty, execution, context, user_message_id)
    except Exception as exc:
        logging.getLogger(__name__).warning("学生自述记忆本轮未保存：%s", type(exc).__name__)
    if context and getattr(context,"extension_state",{}).get("heart_evaluation",{}).get("prepared"):
        if getattr(context,"extension_state",{}).get("heart_evaluation",{}).get("durable_candidate"):
            from integrations.deeptutor.assessment_delivery import deliver_current
            await deliver_current()
        return
    await asyncio.to_thread(record_completed_teaching, execution, context)
    candidate = await asyncio.to_thread(build_snapshot, execution, context, events, user_message_id)
    if candidate:
        await asyncio.to_thread(record_displayed_references, candidate[3], context, events)
        await asyncio.to_thread(jobs.enqueue, *candidate, RULE_VERSION)
