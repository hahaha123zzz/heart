"""派生记忆索引：全历史来源、学生范围内 FTS 与可重建向量缓存。"""
from __future__ import annotations
import hashlib
import json
import re
from sqlalchemy import select, text
from database.database import session_scope
from database.models import (Student, MemoryDocumentRow, ConversationRow, PDFCitationRow,
    FigureCitationRow, EvidenceRow, EventEvidenceRow, LearningEventRow, ExerciseSubmissionRow, MemoryExclusionRow,
    MemoryControlRow)


def memory_terms(value):
    words = set(re.findall(r"[a-zA-Z][a-zA-Z0-9_]*", value.casefold()))
    for run in re.findall(r"[\u4e00-\u9fff]+", value):
        words.update(run[i:i+2] for i in range(len(run)-1))
    return words - {"什么", "如何", "为什么", "怎么", "可以", "这个", "一下", "教材", "解释", "学习", "内容", "用户", "学生"}


def ensure_search_index(engine):
    """PostgreSQL 中文二元组的全文索引；建表后调用一次。"""
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_memory_documents_tsv "
            "ON memory_documents USING gin (to_tsvector('simple', index_text))"
        ))


class MemoryIndexRepository:
    def sync_memory_index(self, student_id):
        """按当前学生扫描完整来源；只写发生变化的派生条目，不生成新的事实。"""
        with session_scope(immediate=True) as session:
            if session.get(Student, student_id) is None:
                return
            epochs={row.knowledge_point:row.epoch for row in session.scalars(
                select(MemoryControlRow).where(MemoryControlRow.student_id==student_id)).all()}
            events = session.scalars(select(LearningEventRow).where(LearningEventRow.student_id == student_id)).all()
            by_conversation = {}
            by_submission = {}
            for item in events:
                payload = item.payload or {}
                ids = payload.get("conversation_ids", []) or ([payload["conversation_id"]] if payload.get("conversation_id") else [])
                for cid in ids:
                    by_conversation[cid] = item
                if payload.get("submission_id"):
                    by_submission[payload["submission_id"]] = item
            citations = {r.conversation_id: r.reference for r in session.scalars(select(PDFCitationRow).join(
                ConversationRow, ConversationRow.id == PDFCitationRow.conversation_id
            ).where(ConversationRow.student_id == student_id)).all()}
            figures = {r.conversation_id: r.figure_ids for r in session.scalars(select(FigureCitationRow).join(
                ConversationRow, ConversationRow.id == FigureCitationRow.conversation_id
            ).where(ConversationRow.student_id == student_id)).all()}
            sources = []
            for row in session.scalars(select(ConversationRow).where(ConversationRow.student_id == student_id)):
                evt = by_conversation.get(row.id)
                if evt and evt.status in ("rolled_back", "conflict") and row.role == "assistant":
                    continue
                ref = {key: value for key, value in (citations.get(row.id) or {}).items()
                       if not key.startswith("_")}
                point = ref.get("section_title") or (evt.knowledge_point if evt else "")
                metadata = {"role": row.role, "verification": "assistant_history" if row.role == "assistant" else "student_statement",
                    "event_id": evt.id if evt else None, "selection_ref": ref or None, "figure_ids": figures.get(row.id, [])}
                sources.append(("conversation", str(row.id), point, row.content, metadata, row.created_at))
            query = select(EvidenceRow, EventEvidenceRow, LearningEventRow).outerjoin(
                EventEvidenceRow, EventEvidenceRow.evidence_id == EvidenceRow.id).outerjoin(
                LearningEventRow, LearningEventRow.id == EventEvidenceRow.event_id).where(EvidenceRow.student_id == student_id)
            for row, link, evt in session.execute(query):
                if row.evidence_type == "tutor_error" or (evt and (evt.student_id != student_id or evt.status in ("rolled_back", "conflict"))):
                    continue
                metadata = {"verification": link.verification if link else "legacy_unverified",
                    "independent": link.independent if link else False, "source_quote": link.source_quote if link else "",
                    "event_id": evt.id if evt else None, "evidence_type": row.evidence_type,
                    "misconception_id": row.misconception_id, "model_confidence": row.confidence}
                if evt:
                    payload=evt.payload or {}
                    metadata.update(selection_ref=payload.get("selection_ref"),question_id=payload.get("question_id"),version=payload.get("version"))
                    if link and evt.event_type == "exercise_submission" and row.evidence_type == "exercise_submission":
                        # 旧链接可能高估验证类别；派生索引按原事件校验，只降级不追认。
                        parts=(payload.get("feedback") or {}).get("parts",[])
                        part=next((p for p in parts if "part:"+str(p.get("part_id")) == link.observation_key),None)
                        if not part or part.get("confirmed") is not True or part.get("method") != "rule":
                            metadata["verification"]="ai_provisional"
                        metadata["independent"]=bool(link.independent and payload.get("assisted") is False)
                sources.append(("evidence",str(row.id),row.knowledge_point,row.content,metadata,row.created_at))
            for row in session.scalars(select(ExerciseSubmissionRow).where(
                    ExerciseSubmissionRow.student_id == student_id, ExerciseSubmissionRow.status == "completed")):
                evt=by_submission.get(row.id)
                result=row.result or {}
                parts=[{k:p.get(k) for k in ("part_id","verdict","score","confirmed","method","feedback")} for p in result.get("parts",[])]
                body=json.dumps({"answers":row.answers,"feedback":parts},ensure_ascii=False)
                metadata={"question_id":row.question_id,"version":row.version,"event_id":evt.id if evt else None,
                    "verification":"rule_verified" if parts and all(p["confirmed"] is True and p["method"] == "rule" for p in parts) else "ai_provisional",
                    "assisted":(evt.payload or {}).get("assisted") if evt else None,
                    "independent":bool(evt and (evt.payload or {}).get("assisted") is False)}
                sources.append(("exercise",row.id,evt.knowledge_point if evt else "",body,metadata,row.created_at))
            excluded={(r.source_kind,r.source_id) for r in session.scalars(select(MemoryExclusionRow).where(MemoryExclusionRow.student_id==student_id))}
            sources=[source for source in sources if (source[0],source[1]) not in excluded]
            for source in sources:
                source[4]["epoch"]=epochs.get(source[2] or "",0)
            old={(r.source_kind,r.source_id):r for r in session.scalars(select(MemoryDocumentRow).where(MemoryDocumentRow.student_id == student_id))}
            seen=set()
            for kind, sid, point, content, metadata, created in sources:
                key=(kind,sid);seen.add(key)
                digest=hashlib.sha256(json.dumps([point,content,metadata],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
                row=old.get(key)
                if row is not None and row.content_hash == digest:
                    row.active=True
                    continue
                if row is None:
                    row=MemoryDocumentRow(student_id=student_id,source_kind=kind,source_id=sid)
                    session.add(row)
                row.knowledge_point=point or "";row.content=content;row.source_metadata=metadata
                row.index_text=" ".join(sorted(memory_terms((point or "")+" "+content)))
                row.content_hash=digest;row.created_at=created;row.embedding=[];row.embedding_model=""
                row.active=True
            for key,row in old.items():
                if key not in seen:
                    row.active=False

    def expire_cards(self, student_id, point=None, epoch=None):
        """删除/更正后让旧卡片失效；mem0 由后台同步删除。"""
        with session_scope(immediate=True) as session:
            query = select(MemoryDocumentRow).where(
                MemoryDocumentRow.student_id == student_id, MemoryDocumentRow.active)
            if point:
                query = query.where(MemoryDocumentRow.knowledge_point == point)
            changed = 0
            for row in session.scalars(query).all():
                if epoch is not None and int((row.source_metadata or {}).get("epoch", 0)) >= int(epoch):
                    continue
                row.active = False
                changed += 1
            return changed

    def memory_documents(self, student_id):
        with session_scope() as session:
            rows=session.scalars(select(MemoryDocumentRow).where(
                MemoryDocumentRow.student_id == student_id, MemoryDocumentRow.active)).all()
            return [self._memory_doc(r) for r in rows]

    @staticmethod
    def _memory_doc(row):
        return {"id":row.id,"source_kind":row.source_kind,"source_id":row.source_id,
            "point":row.knowledge_point,"content":row.content,"metadata":dict(row.source_metadata or {}),
            "created_at":row.created_at.isoformat(),"content_hash":row.content_hash,
            "embedding_model":row.embedding_model,"embedding":list(row.embedding or [])}

    def memory_lexical(self, student_id, query, limit=40):
        terms=sorted(memory_terms(query))[:48]
        if not terms:
            return [],"none"
        with session_scope() as session:
            match=" | ".join(terms)
            rows=session.execute(text(
                "SELECT id FROM memory_documents WHERE student_id=:student AND active "
                "AND to_tsvector('simple', index_text) @@ to_tsquery('simple', :query) "
                "ORDER BY ts_rank_cd(to_tsvector('simple', index_text), to_tsquery('simple', :query)) DESC "
                "LIMIT :limit"),
                {"query":match,"student":student_id,"limit":limit}).all()
            if rows:
                return [r[0] for r in rows],"postgres_tsvector"
        target=set(terms)
        ranked=sorted(((len(target & memory_terms(d["point"]+d["content"])),d["id"]) for d in self.memory_documents(student_id)),reverse=True)
        return [sid for score,sid in ranked[:limit] if score],"lexical_fallback"

    def save_memory_vectors(self, student_id, vectors, model):
        """模型计算之后再次检查来源哈希，删除的学生和条目不重建。"""
        with session_scope(immediate=True) as session:
            for doc_id,digest,values in vectors:
                row=session.get(MemoryDocumentRow,doc_id)
                if row and row.student_id == student_id and row.content_hash == digest:
                    row.embedding_model=model;row.embedding=values
