"""上游负责教材召回，宿主按发布索引重新读取原文后再做精细证据选择。"""
import hashlib
import sqlite3

from knowledge.course_config import COURSE_ID, PSYCHOLOGY_DIR
from knowledge.textbook import terms_for
from llm.client import LLMError
from .client import BackendUnavailable, DeepTutorBackend


def supplement(query, existing, limit=6):
    from knowledge.hybrid_retrieval import _as_chunk

    terms = list(dict.fromkeys([query[:100], *sorted((term for term in terms_for(query) if len(term) >= 2), key=lambda term: (-len(term), term))]))[:8]
    path = PSYCHOLOGY_DIR / "rag_index.sqlite3"
    try:
        result = DeepTutorBackend(timeout=25)._post("/internal/heart/knowledge/search", {"terms": terms, "limit": min(12, max(1, limit))})
        identifiers = result.get("chunk_ids")
        if (result.get("course_id") != COURSE_ID or not isinstance(identifiers, list) or len(identifiers) > 12
                or any(not isinstance(key, str) or len(key) > 200 for key in identifiers)
                or len(identifiers) != len(set(identifiers))):
            raise ValueError("知识库召回身份无效")
        if path.with_name(path.name + "-wal").exists() or hashlib.sha256(path.read_bytes()).hexdigest() != result.get("index_sha256"):
            raise ValueError("上游知识库不属于当前教材索引版本")
        db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        try:
            rows = {key: db.execute("SELECT * FROM chunks WHERE id=?", (key,)).fetchone() for key in identifiers}
        finally:
            db.close()
        if any(row is None for row in rows.values()): raise ValueError("知识库返回未知教材块")
        known = {chunk.chunk_id for chunk in existing}
        extra = [_as_chunk(rows[key]) for key in identifiers if key not in known]
        if not existing: return extra[:limit]
        split = max(1, limit - 2)
        return (existing[:split] + extra[:2] + existing[split:])[:limit]
    except (BackendUnavailable, ValueError, OSError, sqlite3.Error) as exc:
        raise LLMError("DeepTutor 教材知识库暂不可用或版本已变化") from exc
