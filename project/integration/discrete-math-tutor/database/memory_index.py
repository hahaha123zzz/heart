"""派生记忆索引：全历史来源、学生范围内 FTS 与可重建向量缓存。"""
from __future__ import annotations
import hashlib
import json
import re
from sqlalchemy import select, text
from database.database import session_scope
from database.models import (Student, MemoryDocumentRow, ConversationRow, PDFCitationRow,
    FigureCitationRow, EvidenceRow, EventEvidenceRow, LearningEventRow, ExerciseSubmissionRow, MemoryExclusionRow)


def memory_terms(value):
    words = set(re.findall(r"[a-zA-Z][a-zA-Z0-9_]*", value.casefold()))
    for run in re.findall(r"[\u4e00-\u9fff]+", value):
        words.update(run[i:i+2] for i in range(len(run)-1))
    return words - {"什么", "如何", "为什么", "怎么", "可以", "这个", "一下", "教材", "解释", "学习", "内容", "用户", "学生"}


def _fts(session):
    if session.bind.dialect.name != "sqlite":
        return False
    existed = session.scalar(text("SELECT 1 FROM sqlite_master WHERE name='memory_documents_fts'"))
    try:
        session.execute(text("CREATE VIRTUAL TABLE IF NOT EXISTS memory_documents_fts USING fts5(index_text, content='memory_documents', content_rowid='id')"))
        session.execute(text("CREATE TRIGGER IF NOT EXISTS memory_documents_ai AFTER INSERT ON memory_documents BEGIN INSERT INTO memory_documents_fts(rowid,index_text) VALUES(new.id,new.index_text); END"))
        session.execute(text("CREATE TRIGGER IF NOT EXISTS memory_documents_ad AFTER DELETE ON memory_documents BEGIN INSERT INTO memory_documents_fts(memory_documents_fts,rowid,index_text) VALUES('delete',old.id,old.index_text); END"))
        session.execute(text("CREATE TRIGGER IF NOT EXISTS memory_documents_au AFTER UPDATE OF index_text ON memory_documents BEGIN INSERT INTO memory_documents_fts(memory_documents_fts,rowid,index_text) VALUES('delete',old.id,old.index_text); INSERT INTO memory_documents_fts(rowid,index_text) VALUES(new.id,new.index_text); END"))
        if not existed:
            session.execute(text("INSERT INTO memory_documents_fts(memory_documents_fts) VALUES('rebuild')"))
        return True
    except Exception as exc:
        # 只允许缺少 FTS5 能力时降级；其他数据库故障不能吞掉。
        if "no such module: fts5" in str(exc):
            return False
        raise


class MemoryIndexRepository:
    def sync_memory_index(self, student_id):
        """按当前学生扫描完整来源；只写发生变化的派生条目，不生成新的事实。"""
        with session_scope(immediate=True) as session:
            if session.get(Student, student_id) is None:
                return
            _fts(session)
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
                ref = citations.get(row.id) or {}
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
            old={(r.source_kind,r.source_id):r for r in session.scalars(select(MemoryDocumentRow).where(MemoryDocumentRow.student_id == student_id))}
            seen=set()
            for kind, sid, point, content, metadata, created in sources:
                key=(kind,sid);seen.add(key)
                digest=hashlib.sha256(json.dumps([point,content,metadata],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
                row=old.get(key)
                if row is not None and row.content_hash == digest:
                    continue
                if row is None:
                    row=MemoryDocumentRow(student_id=student_id,source_kind=kind,source_id=sid)
                    session.add(row)
                row.knowledge_point=point or "";row.content=content;row.source_metadata=metadata
                row.index_text=" ".join(sorted(memory_terms((point or "")+" "+content)))
                row.content_hash=digest;row.created_at=created;row.embedding=[];row.embedding_model=""
            for key,row in old.items():
                if key not in seen:
                    session.delete(row)

    def memory_documents(self, student_id):
        with session_scope() as session:
            rows=session.scalars(select(MemoryDocumentRow).where(MemoryDocumentRow.student_id == student_id)).all()
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
            if session.bind.dialect.name == "sqlite" and session.scalar(text("SELECT 1 FROM sqlite_master WHERE name='memory_documents_fts'")):
                match=" OR ".join('"'+t+'"' for t in terms)
                rows=session.execute(text("SELECT d.id FROM memory_documents_fts JOIN memory_documents d ON d.id=memory_documents_fts.rowid WHERE memory_documents_fts MATCH :query AND d.student_id=:student ORDER BY bm25(memory_documents_fts) LIMIT :limit"),
                    {"query":match,"student":student_id,"limit":limit}).all()
                return [r[0] for r in rows],"fts5"
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
