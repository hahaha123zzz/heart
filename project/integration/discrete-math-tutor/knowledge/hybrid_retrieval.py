"""结构索引上的关键词与语义混合召回，按需重排。"""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
from array import array
from contextlib import closing
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

from knowledge.textbook import TextbookChunk, retrieve, terms_for
from knowledge.inference_runtime import configured_device, prepare_onnx, verify_device, record_session

from knowledge.logic_formula import extract as extract_formulas, normalize as normalize_formula, search_text as formula_search_text
from knowledge.concept_aliases import expand_query, matched_aliases
from knowledge.course_config import PSYCHOLOGY,PSYCHOLOGY_DIR

INDEX = PSYCHOLOGY_DIR/'rag_index.sqlite3' if PSYCHOLOGY else Path(__file__).resolve().parent / "rag_index_v2.sqlite3"
REFERENCE = re.compile(r"(?:图|表|定理|定义|例|公式)\s*\d+(?:[.．-]\d+)?")
SYMBOL_EXPRESSION = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[∧∨→↔][A-Za-z][A-Za-z0-9]*)+")
QUOTED_PHRASE = re.compile(r"[“「\"]([^”」\"]{2,120})[”」\"]")
OBJECT_QUESTION = re.compile(
    r"(?:问|请问|对于|关于)?\s*([^，。！？；\n]{2,80}?)\s*的?\s*(?:组成对象|元素)"
    r"\s*(?:是谁|是什么|有哪些|是哪些)"
)
FOCUS_BEFORE_DE = re.compile(r"(?:问|请问|对于|关于)?\s*([^的，。！？；\n]{2,40})\s*的")
FUZZY_GENERIC = re.compile(
    r"什么条件(?:下)?|什么时候|什么|怎样|如何|为什么|为何|是否|请问|问|"
    r"组成对[相像]|组成对象|是谁|是什么|有哪些|是哪些|这一集合|集合中的?"
)
SEMANTIC_TERMS = (
    "正整数", "负整数", "非负整数", "非正整数", "自然数", "整数",
    "有限集", "无限集", "空集", "全集", "真子集", "子集",
    "合取", "析取", "否定", "充分必要", "充分", "必要", "当且仅当",
    "单射", "满射", "双射", "有向边", "无向边", "连通", "无圈",
    "自反", "反自反", "对称", "反对称", "传递",
)


def _reference_present(text: str, refs: set[str]) -> bool:
    found = {re.sub(r"\s+", "", match.group()).replace("．", ".")
             for match in REFERENCE.finditer(text)}
    return bool(found & refs)


def _fuse_rankings(prior: list, reranked: list) -> list:
    """两种排序各占一路 RRF，保留符号与教材结构的定位信息。"""
    prior_rank = {row["id"]: rank for rank, (_, row) in enumerate(prior, 1)}
    fused = [(1 / (60 + rank) + 1 / (60 + prior_rank[row["id"]]), row)
             for rank, (_, row) in enumerate(reranked, 1)]
    return sorted(fused, key=lambda item: item[0], reverse=True)


def _compact_fuzzy(value: str) -> str:
    return re.sub(r"[\s“”「」\"'，。！？；：,.!?;:()（）]+", "", value)


def _fuzzy_focus(query: str) -> str:
    candidates = [
        phrase.strip() for phrase in QUOTED_PHRASE.findall(query)
    ]
    candidates += [
        match.group(1).strip() for match in OBJECT_QUESTION.finditer(query)
    ]
    if not candidates:
        match = FOCUS_BEFORE_DE.search(query)
        if match:
            candidates.append(match.group(1).strip())
    if not candidates:
        candidates.append(query)
    for candidate in candidates:
        cleaned = FUZZY_GENERIC.sub("", candidate)
        cleaned = _compact_fuzzy(cleaned)
        if 2 <= len(cleaned) <= 40:
            return cleaned
    return ""


def _protected_terms(value: str) -> set[str]:
    compact = _compact_fuzzy(value)
    return {term for term in SEMANTIC_TERMS if term in compact}


def _damerau_similarity(left: str, right: str) -> float:
    """Normalize edit distance and count one adjacent swap as one edit."""
    rows, cols = len(left) + 1, len(right) + 1
    matrix = [[0] * cols for _ in range(rows)]
    for row in range(rows):
        matrix[row][0] = row
    for col in range(cols):
        matrix[0][col] = col
    for row in range(1, rows):
        for col in range(1, cols):
            cost = 0 if left[row - 1] == right[col - 1] else 1
            matrix[row][col] = min(
                matrix[row - 1][col] + 1,
                matrix[row][col - 1] + 1,
                matrix[row - 1][col - 1] + cost,
            )
            if (row > 1 and col > 1 and left[row - 1] == right[col - 2]
                    and left[row - 2] == right[col - 1]):
                matrix[row][col] = min(matrix[row][col], matrix[row - 2][col - 2] + 1)
    return 1 - matrix[-1][-1] / max(len(left), len(right), 1)


def _fuzzy_score(focus: str, candidate: str) -> float:
    if not focus or not candidate:
        return 0.0
    if _protected_terms(focus) - _protected_terms(candidate):
        return 0.0
    matcher = SequenceMatcher(None, focus, candidate, autojunk=False)
    longest = matcher.find_longest_match(0, len(focus), 0, len(candidate))
    coverage = longest.size / len(focus)
    start = max(0, longest.b - longest.a)
    windows = (
        candidate[start:start + len(focus)],
        candidate[max(0, start - 1):max(0, start - 1) + len(focus)],
        candidate[start:start + len(focus) + 1],
    )
    return max(
        matcher.ratio(),
        coverage,
        *[_damerau_similarity(focus, window) for window in windows if window],
    )


def _chapter_hint(query: str, psychology=False) -> int | None:
    explicit = re.search(r"第\s*(\d+)\s*章|(?:图|表|定理|定义|例|公式)\s*(\d+)[.．-]\d+", query)
    if explicit:
        return int(explicit.group(1) or explicit.group(2))
    if psychology:return None
    if "特殊图" in query or "二部图" in query:
        return 8
    for word, chapter in (("函数", 10), ("关系", 9), ("哈密顿", 7),
                          ("图论", 7), ("空集", 1), ("集合", 1),
                          ("数学归纳", 2), ("牛顿二项式", 3),
                          ("合取", 4), ("命题逻辑", 4), ("谓词逻辑", 5),
                          ("形式系统", 6)):
        if word in query:
            return chapter
    return None


def _definition_subject(query: str) -> str | None:
    match = (re.search(r"^\s*什么是\s*([\u4e00-\u9fff]{2,16})\s*[？?]?\s*$", query)
             or re.search(r"^\s*([\u4e00-\u9fff]{2,16}?)\s*是什么\s*[？?]?\s*$", query))
    if not match:
        return None
    subject = re.sub(r"的(?:定义|性质)$", "", match.group(1))
    return subject if len(subject) >= 2 else None


def _subject_present(db: sqlite3.Connection, subject: str) -> bool:
    aliases = [alias for _, group in matched_aliases(subject) for alias in group]
    if aliases and db.execute("SELECT 1 FROM chunks WHERE " + " OR ".join("lower(text) LIKE ?" for _ in aliases) + " LIMIT 1",
                              tuple("%" + alias.lower() + "%" for alias in aliases)).fetchone():
        return True
    parts = [part for part in re.split(r"[的与和中里]", subject) if len(part) >= 2]
    if not parts:
        parts = [subject]
    condition = " AND ".join("(text || section) LIKE ?" for _ in parts)
    return db.execute(f"SELECT 1 FROM chunks WHERE {condition} LIMIT 1",
                      tuple("%" + part + "%" for part in parts)).fetchone() is not None


def _as_chunk(row: sqlite3.Row, *, text: str | None = None) -> TextbookChunk:
    body = text if text is not None else row["text"]
    return TextbookChunk(
        source=row["source"], section=row["section"], text=body,
        terms=terms_for(body), kind=row["kind"],
        asset_ids=tuple(json.loads(row["asset_ids"] or "[]")),
        section_id=row["section_id"], chunk_id=row["id"],
        parent_id=row["parent_id"], chapter_id=row["chapter_id"],
        page=row["page"], block_start=row["block_start"],
        block_end=row["block_end"],
    )


@lru_cache(maxsize=2)
def _vectors(path: str, modified: int) -> tuple[str | None, list[tuple[str, array, float]]]:
    with closing(sqlite3.connect(path)) as db:
        model_row = db.execute("SELECT value FROM metadata WHERE key='embedding_model'").fetchone()
        if not model_row:
            return None, []
        rows = []
        for chunk_id, data in db.execute("SELECT id,data FROM vectors"):
            values = array("f")
            values.frombytes(data)
            norm = math.sqrt(sum(value * value for value in values)) or 1.0
            rows.append((chunk_id, values, norm))
        return model_row[0], rows


_loaded_embedders = {}


def loaded_embedder(model_name: str):
    """供记忆检索借用已初始化模型；此函数永不创建/下载模型。"""
    return _loaded_embedders.get((model_name, configured_device("EMBED")))


def _embedder(model_name: str):
    return _embedder_on_device(model_name, configured_device("EMBED"))

@lru_cache(maxsize=2)
def _embedder_on_device(model_name: str, device: str):
    from fastembed import TextEmbedding
    model = TextEmbedding(model_name=model_name, **prepare_onnx(device))
    verify_device(model, device)
    record_session("embedding", model, device)
    _loaded_embedders[(model_name, device)] = model
    if len(_loaded_embedders) > 2:
        _loaded_embedders.pop(next(iter(_loaded_embedders)))
    return model


def _reranker(model_name: str):
    return _reranker_on_device(model_name, configured_device("RERANK"))

@lru_cache(maxsize=2)
def _reranker_on_device(model_name: str, device: str):
    if model_name == "BAAI/bge-reranker-v2-m3":
        from FlagEmbedding import FlagReranker
        return "flag", FlagReranker(model_name, use_fp16=False, devices=device)
    from fastembed.rerank.cross_encoder import TextCrossEncoder
    model = TextCrossEncoder(model_name=model_name, threads=4, **prepare_onnx(device))
    verify_device(model, device)
    record_session("reranker", model, device)
    return "fastembed", model


def _expand_parent(db: sqlite3.Connection, row: sqlite3.Row) -> str:
    if row["kind"] != "text":
        return row["text"]
    siblings = db.execute(
        "SELECT text FROM chunks WHERE parent_id=? AND kind='text' ORDER BY id",
        (row["parent_id"],),
    ).fetchall()
    joined = "\n".join(item[0] for item in siblings)
    return joined if len(joined) <= 1300 else row["text"]


def _table_headers(text: str) -> set[str]:
    first_line = next((line for line in text.splitlines() if line.startswith("|")), "")
    return {re.sub(r"\s+", "", cell).lower()
            for cell in first_line.strip("|").split("|")} if first_line else set()


def _primary_unit(row, refs: set[str]) -> bool:
    """明确编号的定义/定理正文优先于背景引用；只处理已经通过检索门槛的候选。"""
    if row["kind"] != "text" or row["section_id"] is None:
        return False
    match=REFERENCE.match(row["text"].lstrip())
    if not match or not match.group().startswith(("定理","定义")):
        return False
    key=re.sub(r"\s+", "", match.group()).replace("．", ".")
    return key in refs

def _select_ranked(db: sqlite3.Connection, ranked: list, terms: frozenset[str],
                   limit: int, *, cross_chapter: bool, refs: set[str] | None = None,
                   preferred_types=(), focus_aliases=(), section_hints=(), trace=None) -> list[TextbookChunk]:
    refs=refs or set()
    def pinned(row):
        return bool(section_hints and any(row["section"].lstrip().startswith(hint)
                                          for hint in section_hints))
    # 稳定分层，不调整模型分数，也不把被门槛拒绝的候选重新放回。
    ranked=sorted(ranked,key=lambda item:(not pinned(item[1]),not _primary_unit(item[1],refs)))
    from knowledge.task_ranking import prefer_task_units, unit_types
    def concept_primary(row):
        # 已通过门槛的结构化定义/定理，与明确概念小节关联；不把绘图邻文当正文。
        return bool(row['section_id'] is not None and unit_types(row) & {'definition','theorem'}
                    and any(len(alias)>=3 and alias in row['section'] for alias in focus_aliases))
    ranked=sorted(ranked,key=lambda item:(not pinned(item[1]),not _primary_unit(item[1],refs),
                                          not concept_primary(item[1])))
    before = [row["id"] for _, row in ranked]
    ranked = prefer_task_units(ranked, preferred_types, is_primary=lambda row: _primary_unit(row, refs))
    ranked = sorted(ranked,key=lambda item:(not pinned(item[1]),-item[0]))
    if trace is not None and preferred_types:
        trace["task_ranking"] = {"preferred_types": list(preferred_types), "before": before,
            "after": [row["id"] for _, row in ranked],
            "types": {row["id"]: sorted(unit_types(row)) for _, row in ranked}}
    selected = []
    seen_parent = set()
    seen_section = set()
    same_section = []
    for _, row in ranked:
        if row["parent_id"] in seen_parent:
            continue
        if (row["section"].lstrip().startswith("第")
                and row["text"].lstrip().startswith("第") and len(row["text"]) < 100):
            continue
        section_key = (row["chapter_id"], row["section"])
        if section_key in seen_section and not _primary_unit(row,refs) and not concept_primary(row):
            same_section.append(row)
            continue
        if (not cross_chapter and selected and row["chapter_id"] != selected[0].chapter_id
                and not (terms & terms_for(row["section"]))):
            continue
        selected.append(_as_chunk(row, text=_expand_parent(db, row)))
        seen_parent.add(row["parent_id"])
        seen_section.add(section_key)
        if len(selected) >= limit:
            break
    for row in same_section:
        if len(selected) >= limit:
            break
        if row["parent_id"] not in seen_parent:
            selected.append(_as_chunk(row, text=_expand_parent(db, row)))
            seen_parent.add(row["parent_id"])
    return selected


def _lexical_supported(db: sqlite3.Connection, query: str, rows: list[sqlite3.Row],
                       refs: set[str], expressions: set[str]) -> bool:
    """无向量时要求候选至少含有可核对的词面线索。"""
    acronyms = set(re.findall(r"(?<![A-Za-z])[A-Z]{2,}(?![A-Za-z])", query))
    for acronym in acronyms:
        if not db.execute("SELECT 1 FROM chunks WHERE (text || section || source) LIKE ? LIMIT 1",
                          ("%" + acronym + "%",)).fetchone():
            return False
    for row in rows:
        content = row["section"] + "\n" + row["text"]
        normalized = re.sub(r"\s+", "", content).replace("．", ".").lower()
        if refs and _reference_present(content, refs):
            return True
        if expressions and any(expression in normalized for expression in expressions):
            return True
        matched = terms_for(query) & terms_for(content)
        if any(len(term) >= 3 for term in matched) or sum(len(term) == 2 for term in matched) >= 2:
            return True
    return False


def retrieve_hybrid(query: str, fallback_chunks: list[TextbookChunk], *, limit: int = 3,
                    trace: dict | None = None, preferred_types=(), index_path: Path | None = None) -> list[TextbookChunk]:
    """索引缺失时沿用旧检索；模型缺失时仍可用 BM25。"""
    if trace is not None:
        trace.clear()
        trace.update(query=query, reranker=os.environ.get("RAG_RERANK_MODEL", "").strip())
    index = INDEX if index_path is None else index_path
    if not index.is_file():
        if index_path is not None:return retrieve(query, fallback_chunks, limit=limit)
        try:
            from scripts.build_rag_index import build_index
            build_index()
        except (OSError, ValueError, KeyError, StopIteration, sqlite3.DatabaseError):
            return retrieve(query, fallback_chunks, limit=limit)
    psychology=PSYCHOLOGY or 'experimental-psychology-3' in index.parts
    search_query = query if psychology else expand_query(normalize_formula(query))
    reranker_query = search_query if psychology else formula_search_text(search_query)
    formula_keys = set() if psychology else {key for _, key in extract_formulas(query)}
    concepts = [] if psychology else matched_aliases(query)
    terms = terms_for(search_query)
    refs = {re.sub(r"\s+", "", match.group()).replace("．", ".") for match in REFERENCE.finditer(query)}
    section_hints = set(re.findall(r"(?<!\d)(\d+(?:\.\d+){1,3})(?!\d)", search_query))
    expressions = set() if psychology else {match.group().lower() for match in SYMBOL_EXPRESSION.finditer(normalize_formula(query))}
    if not terms and not refs and not expressions:
        return []
    scores: dict[str, float] = {}
    try:
        db = sqlite3.connect(index)
        db.row_factory = sqlite3.Row
        try:
            subject = _definition_subject(query)
            subject_missing = bool(subject and not _subject_present(db, subject))
            query_tokens = sorted(terms, key=lambda item: (-len(item), item))[:32]
            match = " OR ".join('"' + item.replace('"', '') + '"' for item in query_tokens)
            lexical = (db.execute(
                "SELECT id FROM chunks_fts WHERE chunks_fts MATCH ? "
                "ORDER BY bm25(chunks_fts) LIMIT 40", (match,),
            ).fetchall() if match else [])
            for rank, row in enumerate(lexical, 1):
                scores[row["id"]] = scores.get(row["id"], 0.0) + 1 / (60 + rank)
            chapter_hint = _chapter_hint(query,psychology=psychology)
            if trace is not None:
                trace.update(lexical_ids=[row["id"] for row in lexical], chapter_hint=chapter_hint)
            if chapter_hint and match:
                local = db.execute(
                    "SELECT c.id FROM chunks_fts JOIN chunks c ON c.id=chunks_fts.id "
                    "WHERE chunks_fts MATCH ? AND c.chapter_id=? "
                    "ORDER BY bm25(chunks_fts) LIMIT 30", (match, chapter_hint),
                ).fetchall()
                for rank, row in enumerate(local, 1):
                    scores[row["id"]] = scores.get(row["id"], 0.0) + 1 / (60 + rank)

            formula_ids = []
            header_ids = set()
            if formula_keys and db.execute("SELECT 1 FROM sqlite_master WHERE name='logic_formulas'").fetchone():
                slots = ",".join("?" for _ in formula_keys)
                matches = db.execute(
                    f"SELECT chunk_id,location FROM logic_formulas WHERE template IN ({slots}) ORDER BY location DESC,chunk_id",
                    tuple(sorted(formula_keys)),
                ).fetchall()
                header_ids = {r["chunk_id"] for r in matches if r["location"] == "header"}
                formula_ids = list(dict.fromkeys([r["chunk_id"] for r in matches if r["location"] == "header"]
                                                + [r["chunk_id"] for r in matches]))[:40]
                for rank, chunk_id in enumerate(formula_ids, 1):
                    scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (60 + rank)
            concept_ids = []
            for _, aliases in concepts:
                clause = " OR ".join("lower(text) LIKE ?" for _ in aliases)
                rows = db.execute(f"SELECT id FROM chunks WHERE {clause} ORDER BY CASE WHEN kind='text' THEN 0 ELSE 1 END,id LIMIT 20",
                                  tuple("%" + alias.lower() + "%" for alias in aliases)).fetchall()
                concept_ids.extend(r["id"] for r in rows)
            concept_ids = list(dict.fromkeys(concept_ids))
            for rank, chunk_id in enumerate(concept_ids, 1):
                scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (60 + rank)
            phrases = QUOTED_PHRASE.findall(query)
            for match in OBJECT_QUESTION.finditer(query):
                phrase = re.sub(r"^\s*(?:问|请问|对于|关于)\s*", "", match.group(1))
                phrase = phrase.strip("“”「」\"' ")
                if phrase:
                    phrases.append(phrase)
            phrases = list(dict.fromkeys(re.sub(r"\s+", "", phrase) for phrase in phrases))
            exact_phrase_ids = []
            if phrases:
                for row in db.execute("SELECT id,text FROM chunks"):
                    compact = re.sub(r"\s+", "", row["text"])
                    if any(phrase in compact for phrase in phrases):
                        exact_phrase_ids.append(row["id"])
                        scores[row["id"]] = scores.get(row["id"], 0.0) + 0.5
            fuzzy_focus = _fuzzy_focus(query) if re.search(r"对象|元素|组成", query) else ""
            fuzzy_ids = []
            if fuzzy_focus and not exact_phrase_ids:
                for row in db.execute("SELECT id,section,text FROM chunks"):
                    sentence_candidates = [
                        value for value in re.split(r"(?<=[。！？；])|\n+", row["text"])
                        if len(_compact_fuzzy(value)) >= 2
                    ][:24]
                    best = max(
                        [_fuzzy_score(fuzzy_focus, _compact_fuzzy(row["section"])),
                         *[_fuzzy_score(fuzzy_focus, _compact_fuzzy(value))
                           for value in sentence_candidates]],
                        default=0.0,
                    )
                    if best >= 0.78:
                        fuzzy_ids.append(row["id"])
                        scores[row["id"]] = scores.get(row["id"], 0.0) + 0.35 * best
            if trace is not None:
                trace.update(concept_ids=concept_ids, formula_ids=formula_ids,
                             formula_templates=sorted(formula_keys), search_query=search_query,
                             quoted_phrases=phrases, exact_phrase_ids=exact_phrase_ids,
                             fuzzy_focus=fuzzy_focus, fuzzy_ids=fuzzy_ids)

            model_name, vectors = _vectors(str(index), index.stat().st_mtime_ns)
            best_dense_score = None
            dense = []
            rerank_model = os.environ.get("RAG_RERANK_MODEL", "").strip()
            if model_name and vectors:
                try:
                    query_vector = list(next(iter(_embedder(model_name).embed([search_query]))))
                    query_norm = math.sqrt(sum(value * value for value in query_vector)) or 1.0
                    dense = sorted(
                        ((sum(a * b for a, b in zip(query_vector, vector)) / (query_norm * norm), chunk_id)
                         for chunk_id, vector, norm in vectors),
                        reverse=True,
                    )[:40]
                    best_dense_score = dense[0][0] if dense else None
                    if trace is not None:
                        trace.update(dense=[{"id": key, "score": float(value)} for value, key in dense])
                    for rank, (_, chunk_id) in enumerate(dense, 1):
                        scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (60 + rank)
                except (ImportError, OSError, ValueError):
                    pass
            if not rerank_model and subject_missing and (best_dense_score is None or best_dense_score < 0.58):
                if trace is not None:
                    trace["rejection"] = "missing_definition_subject"
                return []

            for ref in refs:
                for row in db.execute("SELECT id FROM chunks WHERE replace(text,'．','.') LIKE ? LIMIT 30", ("%" + ref + "%",)):
                    scores[row["id"]] = scores.get(row["id"], 0.0) + 0.1
            for expression in expressions:
                for row in db.execute("SELECT id FROM chunks WHERE lower(text) LIKE ? LIMIT 40", ("%" + expression + "%",)):
                    scores[row["id"]] = scores.get(row["id"], 0.0) + 0.08
            # 相似度低时，词面偶然重合不能充当教材依据。
            if not rerank_model and best_dense_score is not None and best_dense_score < 0.58 and not refs:
                if trace is not None:
                    trace["rejection"] = "dense_threshold"
                return []
            if not scores:
                return []

            ids = sorted(scores, key=scores.get, reverse=True)[:40]
            if rerank_model:
                # 保留两路候选，避免章节加分在重排之前挤掉语义召回。
                ids = list(dict.fromkeys(ids[:12] + [key for _, key in dense[:20]]
                                         + [row["id"] for row in lexical[:20]]
                                         + formula_ids[:8] + concept_ids[:8]))
            candidates = [db.execute("SELECT * FROM chunks WHERE id=?", (chunk_id,)).fetchone() for chunk_id in ids]
            if trace is not None:
                trace["candidates"] = [{"id": row["id"], "chapter": row["chapter_id"],
                                         "section": row["section"], "kind": row["kind"]} for row in candidates]
            if not rerank_model and best_dense_score is None and not _lexical_supported(db, search_query, candidates, refs, expressions):
                return []
            requested_kind = ("table" if re.search(r"表格|真值表|函数表", query)
                              or (re.search(r"何时为真|什么时候为真|真值|取真|取假|为假|赋值", normalize_formula(query))
                                  and re.search(r"合取|析取|蕴涵|[¬∧∨→]", normalize_formula(query)))
                              else "formula" if re.search(r"公式|表达式", query)
                              else "image_context" if re.search(r"配图|插图|图示|图片", query)
                              else None)
            ranked = []
            for row in candidates:
                score = scores[row["id"]]
                if any(row["section"].lstrip().startswith(hint) for hint in section_hints):
                    # 查询扩展或用户明确写出的章节编号是结构定位信号，不替代原文门槛。
                    score += 0.2
                if chapter_hint and row["chapter_id"] == chapter_hint:
                    score += 0.01
                if row["kind"] == requested_kind:
                    score += 0.03
                if row["section"] and row["section"] in query:
                    score += 0.01
                section_label = re.sub(r"^\d+(?:\.\d+)*\s*", "", row["section"]).strip()
                section_overlap = terms & terms_for(section_label)
                score += min(0.09, sum(0.013 if len(term) == 2 else 0.019
                                       for term in section_overlap))
                if len(section_label) >= 3 and section_label in query:
                    score += 0.05
                if expressions and any(expression in re.sub(r"\s+", "", row["text"]).lower()
                                       for expression in expressions):
                    score += 0.08
                if expressions and row["kind"] == "table":
                    if expressions & _table_headers(row["text"]):
                        score += 0.25
                if row["kind"] == "table":
                    headers = _table_headers(row["text"])
                    if any(term in header for term in terms if len(term) >= 3 for header in headers):
                        score += 0.06
                if (re.search(r"定义|是什么", query) and row["kind"] == "text"
                        and re.match(r"^\s*定义\s*\d", row["text"])):
                    score += 0.02
                if "空集" in query and re.search(r"没有任何元素.{0,12}空集", row["text"]):
                    score += 0.05
                if "公理" in query and "公理系统包括" in row["text"]:
                    score += 0.05
                if "范式" not in query and "范式" in row["section"]:
                    score -= 0.02
                if row["kind"] == "image_context" and refs:
                    if _reference_present(row["text"], refs):
                        score += 0.12
                    if "图号未核定" in row["text"]:
                        score -= 0.06
                ranked.append((score, row))
            ranked.sort(key=lambda item: item[0], reverse=True)
            if section_hints:
                pinned_candidates = [(score, row) for score, row in ranked
                                     if any(row["section"].lstrip().startswith(hint)
                                            for hint in section_hints)]
                if pinned_candidates:
                    ranked = pinned_candidates
            if trace is not None:
                trace["ranked"] = [{"id": row["id"], "score": score} for score, row in ranked]
            matched_resource = False
            if refs:
                exact = [(score, row) for score, row in ranked
                         if _reference_present(row["text"], refs)]
                if exact:
                    matched_resource = True
                    if any(row["kind"] == "image_context" and "图号未核定" not in row["text"]
                           for _, row in exact):
                        exact = [(score, row) for score, row in exact
                                 if "图号未核定" not in row["text"]]
                    ranked = exact
            if requested_kind == "table" and expressions:
                exact_tables = [(score, row) for score, row in ranked
                                if row["kind"] == "table" and expressions & _table_headers(row["text"])]
                if exact_tables:
                    matched_resource = True
                    ranked = exact_tables
            # 模板匹配仅缩小真值问题的表格候选，不豁免相关性门槛。
            structural_table = False
            if not matched_resource and requested_kind == "table" and header_ids:
                structural_tables = [(score, row) for score, row in ranked if row["id"] in header_ids]
                if structural_tables:
                    ranked = structural_tables
                    structural_table = True
            if trace is not None:
                trace["structural_table_match"] = structural_table
            reranked = False
            fallback_ranked = ranked
            if rerank_model:
                try:
                    backend, reranker = _reranker(rerank_model)
                    if trace is not None:
                        trace["reranker_device"] = configured_device("RERANK")
                        trace["reranker_query"] = reranker_query
                    top = ranked
                    passages = [row["section"] + "\n" + re.sub(
                        r"(?:formula|image|table)-\d+-\d+", "", row["text"]
                    )[:700] for _, row in top]
                    if formula_keys:
                        passages = [formula_search_text(passage) for passage in passages]
                    if backend == "flag":
                        values = reranker.compute_score([[reranker_query, passage] for passage in passages])
                    else:
                        values = list(reranker.rerank(reranker_query, passages, batch_size=4))
                    if isinstance(values, (int, float)):
                        values = [float(values)]
                    values = [float(value) for value in values]
                    if len(values) != len(top) or not all(math.isfinite(value) for value in values):
                        raise ValueError("reranker returned invalid scores")
                    ranked = sorted(zip(values, (row for _, row in top)), key=lambda item: item[0], reverse=True)
                    reranked = True
                    threshold = float(os.environ.get("RAG_RERANK_MIN_PROBABILITY", "0.15"))
                    if not 0 < threshold < 1:
                        raise ValueError("RAG_RERANK_MIN_PROBABILITY must be between 0 and 1")
                    minimum = math.log(threshold / (1 - threshold))
                    # 精确资源定位靠已匹配的图号/表头；一般问题逐段检查相关性。
                    exact_resource = matched_resource
                    if trace is not None:
                        trace.update(evidence_gate="reranker", reranker_threshold=minimum,
                                     exact_resource=exact_resource,
                                     reranked=[{"id": row["id"], "score": score} for score, row in ranked])
                    if not exact_resource:
                        ranked = [(score, row) for score, row in ranked if score >= minimum]
                    if not ranked:
                        if trace is not None:
                            trace["rejection"] = "reranker_threshold"
                        return []
                    ranked = _fuse_rankings(fallback_ranked, ranked)
                    if trace is not None:
                        trace["fused"] = [{"id": row["id"], "score": score} for score, row in ranked]
                except (ImportError, OSError, ValueError, RuntimeError) as error:
                    reranked = False
                    ranked = fallback_ranked
                    if trace is not None:
                        trace["reranker_error"] = type(error).__name__ + ": " + str(error)
            if not reranked:
                if trace is not None:
                    trace["evidence_gate"] = "fallback"
                if (subject_missing and (best_dense_score is None or best_dense_score < 0.58)
                        or best_dense_score is not None and best_dense_score < 0.58 and not refs
                        or best_dense_score is None and not _lexical_supported(db, query, candidates, refs, expressions)):
                    if trace is not None:
                        trace["rejection"] = "fallback_threshold"
                    return []

            selected = _select_ranked(db, ranked, terms, limit, cross_chapter=reranked, refs=refs,
                                      preferred_types=preferred_types,
                                      focus_aliases=tuple(alias for _, aliases in concepts for alias in aliases),
                                      section_hints=section_hints,trace=trace)
            if trace is not None:
                trace["selected"] = [hit.chunk_id for hit in selected]
                trace["primary_unit_ids"] = [row["id"] for _,row in ranked if _primary_unit(row,refs)]
            return selected
        finally:
            db.close()
    except sqlite3.DatabaseError:
        return retrieve(query, fallback_chunks, limit=limit)
