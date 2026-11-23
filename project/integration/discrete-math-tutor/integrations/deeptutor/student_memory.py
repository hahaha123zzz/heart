"""新学生记忆只从 H PG 读取；不扫描旧聊天或厂家记忆文件。"""
from __future__ import annotations

import asyncio
from contextvars import ContextVar
from dataclasses import dataclass
from hashlib import sha256
import logging
import os
import re
from pathlib import Path
import threading
import json
from uuid import uuid4

from sqlalchemy import select
from database.database import engine, session_scope
from database.models import Base, Student, StudentMemorySetting, MemoryDocumentRow, LearningEventRow

SOURCE = "student_memory"
_query_context = ContextVar("student_memory_query", default=None)
_mem0_client = None
_mem0_attempted = False
_mem0_lock = threading.Lock()
_summary_fingerprint = ContextVar("student_memory_summary_fingerprint", default=None)
_STAMP = re.compile(r"^\[HEART_MEMORY:([a-f0-9]{64})\]$", re.MULTILINE)


def ensure_tables():
    Base.metadata.create_all(engine, tables=[Student.__table__, StudentMemorySetting.__table__, MemoryDocumentRow.__table__])


def _setting(session, owner, vendor_user_id, *, create=False):
    row = session.get(StudentMemorySetting, owner)
    if row is not None and row.vendor_user_id != vendor_user_id:
        raise ValueError("memory_identity_changed")
    if row is None and create:
        row = StudentMemorySetting(student_id=owner, vendor_user_id=vendor_user_id, enabled=True, revision=0)
        session.add(row)
        session.flush()
    return row


def settings(owner, vendor_user_id):
    with session_scope() as session:
        row = _setting(session, owner, vendor_user_id)
        return {"enabled": row.enabled if row else True, "revision": row.revision if row else 0}


def set_enabled(owner, vendor_user_id, enabled):
    with session_scope(immediate=True) as session:
        row = _setting(session, owner, vendor_user_id, create=True)
        if row.enabled != enabled:
            row.enabled = enabled
            row.revision += 1
        return {"enabled": row.enabled, "revision": row.revision}


def _query(owner, vendor_user_id):
    return select(MemoryDocumentRow).where(MemoryDocumentRow.student_id == owner,
        MemoryDocumentRow.source_kind == SOURCE, MemoryDocumentRow.active,
        MemoryDocumentRow.source_metadata["vendor_user_id"].as_string() == vendor_user_id)


def _card(row):
    meta = row.source_metadata or {}
    return {"id": str(row.id), "text": row.content, "kind": meta.get("kind"),
            "source": meta.get("verification"), "created_at": row.created_at.isoformat(),
            "version": row.content_hash}


def overview(owner, vendor_user_id, *, for_generation=False, limit=200, search=""):
    with session_scope() as session:
        control = _setting(session, owner, vendor_user_id)
        if for_generation and control is not None and not control.enabled:
            return {"preferences": [], "profile": [], "has_more": False}
        query = _query(owner, vendor_user_id)
        if search:
            query = query.where(MemoryDocumentRow.content.contains(search, autoescape=True))
        rows = session.scalars(query.order_by(MemoryDocumentRow.created_at.desc(),
            MemoryDocumentRow.id.desc()).limit(limit + 1)).all()
        cards = [_card(row) for row in rows[:limit]]
        return {"preferences": [c for c in cards if c["kind"] == "preference"],
                "profile": [c for c in cards if c["kind"] == "profile"], "has_more": len(rows) > limit}


def add_preference(owner, vendor_user_id, text):
    text = text.strip()
    if not text or len(text) > 500:
        raise ValueError("invalid_preference")
    normalized = " ".join(text.split()).casefold()
    with session_scope(immediate=True) as session:
        _setting(session, owner, vendor_user_id, create=True)
        if session.get(Student, owner) is None:
            session.add(Student(student_id=owner))
            session.flush()
        existing = session.scalars(_query(owner, vendor_user_id)).all()
        for row in existing:
            if row.source_metadata.get("kind") == "preference" and " ".join(row.content.split()).casefold() == normalized:
                return _card(row)
        row = MemoryDocumentRow(student_id=owner, source_kind=SOURCE, source_id=uuid4().hex, knowledge_point="",
            content=text, index_text=normalized, content_hash=sha256(text.encode()).hexdigest(),
            source_metadata={"vendor_user_id": vendor_user_id, "kind": "preference", "verification": "explicit_user", "epoch": 0})
        session.add(row)
        session.flush()
        return _card(row)


def delete_entry(owner, vendor_user_id, kind, entry_id):
    with session_scope(immediate=True) as session:
        control = _setting(session, owner, vendor_user_id, create=True)
        row = session.scalar(_query(owner, vendor_user_id).where(MemoryDocumentRow.id == entry_id))
        if row is None or row.source_metadata.get("kind") != kind:
            return False
        row.active = False
        control.revision += 1
        return True


def get_mem0():
    global _mem0_client, _mem0_attempted
    snapshot = Path(os.getenv("LIGHTRAG_EMBED_SNAPSHOT", ""))
    if os.getenv("MEM0_ENABLED", "0") != "1" or not snapshot.is_dir() or not any(snapshot.glob("*.onnx")):
        return None
    with _mem0_lock:
        if not _mem0_attempted:
            _mem0_attempted = True
            try:
                from memory.mem0_store import Mem0Store
                _mem0_client = Mem0Store(enabled=True)
            except Exception as exc:
                logging.getLogger(__name__).warning("学生 mem0 暂不可用：%s", type(exc).__name__)
        return _mem0_client


def current_catalog_version():
    from integrations.deeptutor.assessment_intake import confirmed_catalog
    return confirmed_catalog()[1]


def _eligible_profile(catalog_version):
    if not catalog_version:
        from sqlalchemy import false
        return false()
    doc = MemoryDocumentRow
    event = LearningEventRow
    meta = doc.source_metadata
    assessment = select(event.id).where(
        event.id == meta["event_id"].as_string(), event.student_id == doc.student_id,
        event.knowledge_point == doc.knowledge_point, event.event_type == "vendor_assessment", event.status == "synced",
        event.payload["job_id"].as_string() == meta["job_id"].as_string(),
        event.payload["vendor_user_id"].as_string() == meta["vendor_user_id"].as_string(),
        event.payload["assessment"]["visual_context"]["catalog_version"].as_string() == catalog_version,
    ).exists()
    self_report = (meta["verification"].as_string() == "student_statement") & (
        meta["rule_version"].as_string() == "explicit-chat-difficulty-v1")
    inference = (meta["verification"].as_string() == "learning_inference") & assessment
    return (meta["kind"].as_string() == "profile") & (meta["catalog_version"].as_string() == catalog_version) & (self_report | inference)


def generation_cards(owner, vendor_user_id, query=""):
    # mem0 的正文不可信，只取编号；等待检索期间发生的删除和开关变化须重读 PG。
    if not settings(owner, vendor_user_id)["enabled"]:
        return {"preferences": [], "profile": []}
    hits = []
    if query:
        try:
            store = get_mem0()
            hits = store.search(owner, query[:2000], limit=20) if store is not None else []
        except Exception:
            hits = []
    if not isinstance(hits, list):
        hits = []
    with session_scope() as session:
        control = _setting(session, owner, vendor_user_id)
        if control is not None and not control.enabled:
            return {"preferences": [], "profile": []}
        preferences = session.scalars(_query(owner, vendor_user_id).where(
            MemoryDocumentRow.source_metadata["kind"].as_string() == "preference").order_by(MemoryDocumentRow.id.desc()).limit(20)).all()
        profile_query = _query(owner, vendor_user_id).where(_eligible_profile(current_catalog_version()))
        profiles, seen = [], set()
        for hit in hits[:20]:
            if (not isinstance(hit, dict) or type(hit.get("card_id")) is not int
                    or not 0 < hit["card_id"] <= 2147483647 or not isinstance(hit.get("memory_id"), str)
                    or not 0 < len(hit["memory_id"]) <= 64):
                continue
            row = session.scalar(profile_query.where(MemoryDocumentRow.id == hit["card_id"]))
            if (row is not None and row.id not in seen
                    and row.mem0_id == hit["memory_id"] and row.mem0_synced_hash == row.content_hash):
                profiles.append(row); seen.add(row.id)
        if not profiles:
            profiles = session.scalars(profile_query.order_by(MemoryDocumentRow.id.desc()).limit(10)).all()
        return {"preferences": [_card(row) for row in preferences], "profile": [_card(row) for row in profiles]}


@dataclass(frozen=True)
class MemoryTurnState:
    owner: str
    vendor_user_id: str
    session_id: str
    turn_id: str
    enabled: bool
    revision: int


def control_for_turn(context, user, execution):
    state = getattr(context, "extension_state", {}).get("heart_memory", {}).get("control")
    if (isinstance(state, MemoryTurnState) and state.owner == user.username and state.vendor_user_id == user.id
            and state.session_id == execution.session_id and state.turn_id == execution.turn_id):
        return {"enabled": state.enabled, "revision": state.revision}
    return None


def _clean_model_history(messages):
    if not isinstance(messages, list):
        return messages
    messages = [message for message in messages if isinstance(message, dict)]
    removed = {call.get("id") for message in messages
               for call in (message.get("tool_calls") if isinstance(message.get("tool_calls"), list) else [])
               if isinstance(call, dict) and isinstance(call.get("id"), str) and call["id"]
               and isinstance(call.get("function"), dict)
               and call["function"].get("name") in {"read_memory", "write_memory"}}
    output = []
    for original in messages:
        if "memory" in str(original.get("_context_snapshot", "")).lower() or original.get("tool_call_id") in removed:
            continue
        message = {key: value for key, value in original.items() if key != "_provider_response_state"}
        if isinstance(message.get("tool_calls"), list):
            message["tool_calls"] = [call for call in message["tool_calls"] if not isinstance(call, dict) or call.get("id") not in removed]
            if not message["tool_calls"]:
                message.pop("tool_calls")
                if not message.get("content"):
                    continue
        output.append(message)
    return output


def fingerprint(owner, vendor_user_id):
    with session_scope() as session:
        control = _setting(session, owner, vendor_user_id)
        enabled = control.enabled if control else True
        revision = control.revision if control else 0
        rows = session.execute(_query(owner, vendor_user_id).where(
            (MemoryDocumentRow.source_metadata["kind"].as_string() == "preference")
            | _eligible_profile(current_catalog_version())).with_only_columns(
            MemoryDocumentRow.id, MemoryDocumentRow.content_hash).order_by(MemoryDocumentRow.id)).all() if enabled else []
        return sha256(json.dumps([owner, vendor_user_id, enabled, revision, [list(row) for row in rows]], ensure_ascii=False).encode()).hexdigest()


def _stamp(text):
    found = _STAMP.search(str(text or ""))
    return found[1] if found else None


async def prepare_history(session_id, session, messages, store):
    from copy import deepcopy
    from deeptutor.multi_user.context import get_current_user_or_none
    user = get_current_user_or_none()
    _summary_fingerprint.set(None)
    if user is None or user.is_admin:
        return session, messages
    try:
        current = await asyncio.to_thread(fingerprint, user.username, user.id)
    except Exception:
        current = None
    _summary_fingerprint.set(current)
    session, messages = dict(session), [m for m in deepcopy(messages) if isinstance(m, dict)]
    if current is None or _stamp(session.get("compressed_summary")) != current:
        session.update(compressed_summary="", summary_up_to_msg_id=0)
        await store.update_summary(session_id, "", 0)
    for message in messages:
        meta = dict(message["metadata"]) if isinstance(message.get("metadata"), dict) else {}
        meta.pop("provider_response_state", None)
        record = meta.get("model_turn")
        if isinstance(record, dict):
            record = dict(record)
            record["messages"] = _clean_model_history(record.get("messages"))
            record.pop("system", None)
            record.pop("request_fingerprint", None)
            meta["model_turn"] = record
        message["metadata"] = meta
    return session, messages


def wrap_summary(text):
    stamp = _summary_fingerprint.get()
    return "[HEART_MEMORY:" + stamp + "]\n" + text if stamp else text


async def prepare_turn(context):
    from deeptutor.multi_user.context import get_current_user_or_none
    user = get_current_user_or_none()
    _query_context.set(None)
    if user is None or user.is_admin:
        return
    context.extension("heart_memory").pop("control", None)
    context.memory_context = ""
    context.runtime.model_history = _clean_model_history(context.runtime.model_history)
    context.conversation_history = _clean_model_history(context.conversation_history)
    context.runtime.previous_model_turn = None
    context.runtime.provider_response_state = None
    try:
        current = await asyncio.to_thread(fingerprint, user.username, user.id)
        for field in ("model_history",):
            history = getattr(context.runtime, field)
            if isinstance(history, list):
                setattr(context.runtime, field, [m for m in history if m.get("role") != "system" or _stamp(m.get("content")) == current])
        context.conversation_history = [m for m in context.conversation_history if m.get("role") != "system" or _stamp(m.get("content")) == current]
        context.metadata["conversation_summary"] = ""
        context.metadata["conversation_context_text"] = ""
        control = await asyncio.to_thread(settings, user.username, user.id)
        context.extension("heart_memory")["control"] = MemoryTurnState(user.username, user.id, context.session_id,
            str(context.metadata.get("turn_id") or ""), control["enabled"], control["revision"])
        _query_context.set((user.username, user.id, context.user_message))
        if control["enabled"]:
            context.memory_context = await asyncio.to_thread(StudentMemoryStore(user.username, user.id).read_l3_concat)
    except Exception:
        context.memory_context = ""
        if isinstance(context.runtime.model_history, list):
            context.runtime.model_history = [m for m in context.runtime.model_history if m.get("role") != "system"]
        context.conversation_history = [m for m in context.conversation_history if m.get("role") != "system"]
        context.metadata["conversation_summary"] = ""
        context.metadata["conversation_context_text"] = ""


# shortcut: 只采集能完整匹配目录的明确自述，更多自然表述待有可核验归因后接入。
_DIFFICULTY = re.compile(r"我(?:目前|现在|总是|还是|一直|总|仍然)?(?:搞不懂|不理解|没理解|没学会|不太懂|不懂)(?P<point>[^，。！？、；：]{2,60})")
_CONFUSION = re.compile(r"我(?:目前|现在|总是|还是|一直|总|仍然)?(?:把(?P<a>[^，。！？、；：]{2,60})和(?P<b>[^，。！？、；：]{2,60})(?:搞混|弄混|混淆)|(?:分不清|容易混淆)(?P<c>[^，。！？、；：]{2,60})和(?P<d>[^，。！？、；：]{2,60}))")


def match_chat_difficulty(text, catalog):
    terms = {}
    for point_id, point in catalog.items():
        name = point["name"]
        for term in {name, name.removesuffix("及控制"), *point.get("aliases", [])}:
            if len(term) >= 2:
                terms.setdefault(term, set()).add(point_id)
    text = text.strip().removesuffix("。").strip()
    for pattern in (_DIFFICULTY, _CONFUSION):
        match = pattern.fullmatch(text)
        if not match:
            continue
        matches = [terms.get(value.strip(), set()) for value in match.groups() if value]
        if all(len(ids) == 1 for ids in matches):
            ids = sorted({next(iter(ids)) for ids in matches})
            if len(ids) == len(matches):
                return ids
    return []


def record_chat_difficulty(execution, context, message_id):
    from deeptutor.multi_user.context import get_current_user_or_none
    from integrations.deeptutor.assessment_intake import confirmed_catalog
    user = get_current_user_or_none()
    if (not user or user.is_admin or not context or context.attachments
            or context.active_capability not in {None, "", "chat"}
            or execution.payload.get("mastery_answer") or type(message_id) is not int or message_id <= 0
            or context.metadata.get("persisted_assistant_has_content") is not True):
        return False
    token = control_for_turn(context, user, execution)
    if not token or not token["enabled"]:
        return False
    text = execution.payload.get("content")
    if not isinstance(text, str) or len(text) > 160:
        return False
    catalog, version = confirmed_catalog()
    ids = match_chat_difficulty(text, catalog)
    if not ids:
        return False
    names = [catalog[point_id]["name"] for point_id in ids]
    content = f"学生自述：理解「{names[0]}」有困难。" if len(ids) == 1 else f"学生自述：容易混淆「{names[0]}」和「{names[1]}」。"
    # 一个目录版本内重复说同一困难不创建第二张卡，也不会撤销用户删除。
    source_id = "chat-self:" + sha256(json.dumps([user.id, version, ids], ensure_ascii=False).encode()).hexdigest()[:54]
    with session_scope(immediate=True) as session:
        control = _setting(session, user.username, user.id, create=True)
        if not control.enabled or control.revision != token["revision"]:
            return False
        if session.scalar(select(MemoryDocumentRow.id).where(MemoryDocumentRow.student_id == user.username,
                MemoryDocumentRow.source_kind == SOURCE, MemoryDocumentRow.source_id == source_id)) is not None:
            return False
        if session.get(Student, user.username) is None:
            session.add(Student(student_id=user.username))
            session.flush()
        session.add(MemoryDocumentRow(student_id=user.username, source_kind=SOURCE, source_id=source_id,
            knowledge_point=ids[0], content=content, index_text=content, content_hash=sha256(content.encode()).hexdigest(),
            source_metadata={"vendor_user_id": user.id, "kind": "profile", "verification": "student_statement",
                "session_id": execution.session_id, "turn_id": execution.turn_id, "message_id": message_id,
                "knowledge_point_ids": ids, "catalog_version": version, "epoch": control.revision,
                "rule_version": "explicit-chat-difficulty-v1"}))
        return True


def record_assessment_memory(session, job, receipt, event_id):
    """与 H 评分同步同一事务，只整理已有依据，不调用模型或扫描历史。"""
    token = (job.input or {}).get("memory_control")
    if not isinstance(token, dict):
        return False
    if receipt.get("student_id") != job.student_id or receipt.get("vendor_user_id") != job.vendor_user_id:
        return False
    reassessment = (job.input or {}).get("reassessment")
    if reassessment:
        original = session.scalar(select(MemoryDocumentRow).where(MemoryDocumentRow.student_id == job.student_id,
            MemoryDocumentRow.source_kind == SOURCE, MemoryDocumentRow.source_id == "assessment:" + reassessment["original_job_id"],
            MemoryDocumentRow.source_metadata["vendor_user_id"].as_string() == job.vendor_user_id))
        if original is not None:
            original.active = False
    if token.get("enabled") is not True or type(token.get("revision")) is not int:
        return False
    control = _setting(session, job.student_id, job.vendor_user_id, create=True)
    if not control.enabled or control.revision != token["revision"]:
        return False
    source_id = "assessment:" + job.id
    existing = session.scalar(select(MemoryDocumentRow).where(MemoryDocumentRow.student_id == job.student_id,
        MemoryDocumentRow.source_kind == SOURCE, MemoryDocumentRow.source_id == source_id))
    if existing is not None:
        return False
    judgment = (job.result or {}).get("judgment") or {}
    kp_id = receipt["knowledge_point_id"]
    point = next((p for p in job.input.get("targets", []) if p.get("id") == kp_id), None)
    if point is None or type(judgment.get("passed")) is not bool:
        return False
    text = "未确认的学习线索：在「" + point["name"] + "」的一次解释中，系统评分为" + ("通过" if judgment["passed"] else "未通过") + "。这只记录本次表现，不代表独立掌握，需要后续作答核验。"
    session.add(MemoryDocumentRow(student_id=job.student_id, source_kind=SOURCE, source_id=source_id,
        knowledge_point=kp_id, content=text, index_text=text, content_hash=sha256(text.encode()).hexdigest(),
        source_metadata={"vendor_user_id": job.vendor_user_id, "kind": "profile", "verification": "learning_inference",
            "event_id": event_id, "job_id": job.id, "catalog_version": job.input.get("catalog_version"),
            "epoch": control.revision, "rule_version": "assessment-observation-v1",
            "assessment_rule_version": getattr(job, "rule_version", ""), "independent": False}))
    return True


async def index_loop():
    from memory.mem0_indexer import Mem0Indexer
    while True:
        try:
            store = await asyncio.to_thread(get_mem0)
            if store is not None:
                await asyncio.to_thread(Mem0Indexer(None, store, source_kind=SOURCE).run_once)
        except Exception as exc:
            logging.getLogger(__name__).warning("学生记忆索引等待恢复：%s", type(exc).__name__)
        await asyncio.sleep(5)


class StudentMemoryStore:
    """厂家 facade 的学生投影；自动线索只由有依据的评估同步产生。"""
    def __init__(self, owner, vendor_user_id):
        self.owner, self.vendor_user_id = owner, vendor_user_id

    def read_doc(self, layer, key):
        from deeptutor.services.memory.document import Document, Entry
        doc = Document(title="学习偏好" if key == "preferences" else "学习画像")
        if layer != "L3" or key not in {"preferences", "profile"}:
            return doc
        try:
            cards = overview(self.owner, self.vendor_user_id)[key]
        except Exception:
            return doc
        doc.sections = [(doc.title, [Entry(id=c["id"], section=doc.title, text=c["text"]) for c in cards])]
        return doc

    def read_raw(self, layer, key):
        if layer != "L3" or key not in {"preferences", "profile"}:
            return ""
        try:
            active = _query_context.get()
            query = active[2] if active and active[:2] == (self.owner, self.vendor_user_id) else ""
            cards = generation_cards(self.owner, self.vendor_user_id, query)[key]
        except Exception:
            return ""
        if not cards:
            return ""
        return "以下偏好与学习信息不代表已核验能力；明确设置和本轮要求优先：\n" + "\n".join(json.dumps(c["text"], ensure_ascii=False) for c in cards)

    def read_l3_concat(self):
        try:
            active = _query_context.get()
            query = active[2] if active and active[:2] == (self.owner, self.vendor_user_id) else ""
            cards = generation_cards(self.owner, self.vendor_user_id, query)
        except Exception:
            return ""
        items = cards["preferences"] + cards["profile"]
        if not items:
            return ""
        return "以下偏好与学习信息不代表已核验能力；明确设置和本轮要求优先：\n" + "\n".join(json.dumps(c["text"], ensure_ascii=False) for c in items)

    async def emit(self, event):
        # 不将聊天全文再写入厂家 L1 文件。
        return None

    async def write_preference(self, **kwargs):
        from deeptutor.services.memory.ops import ApplyReport
        return ApplyReport(accepted=False, reason="请在我的记忆页主动添加偏好；聊天工具不能静默新增或更正长期记忆。")

    async def overwrite_doc(self, *args, **kwargs):
        from deeptutor.services.memory.paths import MemoryAccessDisabledError
        raise MemoryAccessDisabledError("学生记忆不支持整篇覆写。")

    delete_entry = overwrite_doc

    async def apply_ops_payload(self, *args, **kwargs):
        return await self.write_preference()

    update_l2 = overwrite_doc
    update_l3 = overwrite_doc

    def overview(self):
        return []
