"""Build and query complete definition, theorem and section knowledge units."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
from array import array
from collections import OrderedDict
from contextlib import closing
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from knowledge.concept_aliases import expand_query
from knowledge.query_understanding import understand
from knowledge.textbook import TextbookChunk, terms_for


ROOT = Path(__file__).resolve().parents[1]
SOURCE_INDEX = ROOT / "knowledge/rag_index_v2.sqlite3"
DEFAULT_INDEX = ROOT / ".runtime/textbook-units-v1.sqlite3"
UNIT_HEADING = re.compile(
    r"(?<![A-Za-z0-9])(定义|定理|推论|引理|命题|例)\s*(\d+)\s*[.．]\s*(\d+)(?![A-Za-z0-9])"
)
EXERCISE_HEADING = re.compile(r"(?<![A-Za-z0-9])(?:练习|习题)\s*\d+")
INLINE_REFERENCE_TAIL = re.compile(
    r"^(?:的|中|可知|说明|就是|是|与|和|或|及|作为|称为|可|有|证明|指)"
)


@dataclass(frozen=True)
class KnowledgeUnit:
    id: str
    label: str
    kind: str
    chapter_id: int
    section_id: int
    section: str
    source: str
    page: int | None
    text: str

    def chunk(self) -> TextbookChunk:
        return TextbookChunk(
            source=self.source,
            section=self.section,
            text=self.text,
            terms=terms_for(self.text),
            kind=self.kind,
            section_id=self.section_id,
            chunk_id=self.id,
            parent_id=self.id,
            chapter_id=self.chapter_id,
            page=self.page,
        )


def _chunk_offsets(rows) -> tuple[str, list[tuple[int, int, sqlite3.Row]]]:
    parts = []
    offsets = []
    cursor = 0
    for row in rows:
        text = row["text"].strip()
        if parts:
            cursor += 1
        offsets.append((cursor, cursor + len(text), row))
        parts.append(text)
        cursor += len(text)
    return "\n".join(parts), offsets


def _page_for(offsets, start: int, end: int, fallback: int | None) -> int | None:
    pages = [
        row["page"] for left, right, row in offsets
        if right > start and left < end and row["page"] is not None
    ]
    return min(pages) if pages else fallback


def extract_units(rows) -> list[KnowledgeUnit]:
    grouped: OrderedDict[tuple[int, int, str], list[sqlite3.Row]] = OrderedDict()
    for row in rows:
        grouped.setdefault(
            (int(row["chapter_id"]), int(row["section_id"]), row["section"]),
            [],
        ).append(row)
    units = []
    seen_ids: set[str] = set()
    for (chapter_id, section_id, section), section_rows in grouped.items():
        text, offsets = _chunk_offsets(section_rows)
        headings = []
        for match in UNIT_HEADING.finditer(text):
            if int(match.group(2)) != chapter_id:
                continue
            before = text[max(0, match.start() - 4):match.start()]
            if before and not re.search(r"(?:^|[\n。！？；,，])\s*$", before):
                continue
            tail = text[match.end():match.end() + 20].lstrip()
            if INLINE_REFERENCE_TAIL.match(tail):
                continue
            headings.append(match)
        first_heading = headings[0].start() if headings else len(text)
        intro_end_match = EXERCISE_HEADING.search(text, 0, first_heading)
        intro_end = intro_end_match.start() if intro_end_match else first_heading
        intro = text[:intro_end].strip()
        source = section_rows[0]["source"]
        fallback_page = min(
            (row["page"] for row in section_rows if row["page"] is not None),
            default=None,
        )
        if len(intro) >= 40:
            units.append(KnowledgeUnit(
                id=f"ch{chapter_id}-s{section_id}-context",
                label="",
                kind="context",
                chapter_id=chapter_id,
                section_id=section_id,
                section=section,
                source=source,
                page=_page_for(offsets, 0, intro_end, fallback_page),
                text=intro,
            ))
        for index, heading in enumerate(headings):
            next_start = headings[index + 1].start() if index + 1 < len(headings) else len(text)
            exercise = EXERCISE_HEADING.search(text, heading.end(), next_start)
            end = exercise.start() if exercise else next_start
            body = text[heading.start():end].strip()
            if len(body) < 20:
                continue
            label = f"{heading.group(1)}{int(heading.group(2))}.{int(heading.group(3))}"
            kind = {
                "定义": "definition",
                "定理": "theorem",
                "推论": "corollary",
                "引理": "lemma",
                "命题": "proposition",
                "例": "example",
            }[heading.group(1)]
            unit_id = f"ch{chapter_id}-s{section_id}-{kind}-{label}"
            if unit_id in seen_ids:
                continue
            seen_ids.add(unit_id)
            units.append(KnowledgeUnit(
                id=unit_id,
                label=label,
                kind=kind,
                chapter_id=chapter_id,
                section_id=section_id,
                section=section,
                source=source,
                page=_page_for(offsets, heading.start(), end, fallback_page),
                text=body,
            ))
    return units


def build_unit_index(
    *,
    source_index: Path = SOURCE_INDEX,
    target: Path = DEFAULT_INDEX,
    embed: bool = False,
    model_name: str = "BAAI/bge-small-zh-v1.5",
) -> dict:
    if not source_index.is_file():
        raise FileNotFoundError(source_index)
    target.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source_index)) as db:
        db.row_factory = sqlite3.Row
        rows = list(db.execute(
            "SELECT id,chapter_id,section_id,source,section,page,text "
            "FROM chunks WHERE section_id IS NOT NULL "
            "ORDER BY chapter_id,section_id,id"
        ))
    units = extract_units(rows)
    temporary = target.with_suffix(".building.sqlite3")
    temporary.unlink(missing_ok=True)
    with closing(sqlite3.connect(temporary)) as db:
        db.executescript(
            """
            CREATE TABLE units (
                id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                kind TEXT NOT NULL,
                chapter_id INTEGER NOT NULL,
                section_id INTEGER NOT NULL,
                section TEXT NOT NULL,
                source TEXT NOT NULL,
                page INTEGER,
                text TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE units_fts USING fts5(id UNINDEXED,tokens);
            CREATE TABLE vectors(id TEXT PRIMARY KEY,data BLOB NOT NULL);
            CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            """
        )
        for unit in units:
            db.execute(
                "INSERT INTO units VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    unit.id,
                    unit.label,
                    unit.kind,
                    unit.chapter_id,
                    unit.section_id,
                    unit.section,
                    unit.source,
                    unit.page,
                    unit.text,
                ),
            )
            tokens = terms_for(
                unit.label + " " + unit.section + " " + unit.text
            )
            db.execute(
                "INSERT INTO units_fts VALUES (?,?)",
                (unit.id, " ".join(sorted(tokens))),
            )
        source_sha = hashlib.sha256(source_index.read_bytes()).hexdigest()
        db.execute("INSERT INTO metadata VALUES ('source_sha256',?)", (source_sha,))
        db.execute("INSERT INTO metadata VALUES ('unit_count',?)", (str(len(units)),))
        if embed:
            from fastembed import TextEmbedding

            model = TextEmbedding(model_name=model_name, cuda=False)
            documents = [
                unit.label + "\n" + unit.section + "\n" + unit.text[:1600]
                for unit in units
            ]
            for unit, vector in zip(units, model.embed(documents, batch_size=32)):
                db.execute(
                    "INSERT INTO vectors VALUES (?,?)",
                    (unit.id, array("f", vector).tobytes()),
                )
            db.execute(
                "INSERT INTO metadata VALUES ('embedding_model',?)",
                (model_name,),
            )
        db.commit()
    temporary.replace(target)
    return {
        "units": len(units),
        "by_kind": {
            kind: sum(unit.kind == kind for unit in units)
            for kind in sorted({unit.kind for unit in units})
        },
        "source_sha256": hashlib.sha256(source_index.read_bytes()).hexdigest(),
        "embedding_model": model_name if embed else None,
        "target": str(target),
    }


def _unit(vector) -> tuple[float, ...]:
    values = tuple(float(value) for value in vector)
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return tuple(value / norm for value in values)


@lru_cache(maxsize=2)
def _unit_vectors(path: str, modified_ns: int):
    del modified_ns
    with closing(sqlite3.connect(path)) as db:
        model_row = db.execute(
            "SELECT value FROM metadata WHERE key='embedding_model'"
        ).fetchone()
        if not model_row:
            return None, []
        rows = []
        for unit_id, data in db.execute("SELECT id,data FROM vectors"):
            vector = array("f")
            vector.frombytes(data)
            vector = _unit(vector)
            rows.append((unit_id, vector, 1.0))
        return model_row[0], rows


@lru_cache(maxsize=1)
def _model(model_name: str):
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=model_name, cuda=False)


def retrieve_units(
    query: str,
    *,
    limit: int = 3,
    index_path: Path = DEFAULT_INDEX,
    section_hints: tuple[int, ...] = (),
) -> list[TextbookChunk]:
    if not index_path.is_file():
        return []
    understanding = understand(query)
    expanded = expand_query(query)
    if understanding.related_concepts:
        expanded += "\n教材术语：" + "、".join(understanding.related_concepts)
    tokens = sorted(terms_for(expanded), key=lambda value: (-len(value), value))[:40]
    if not tokens:
        return []
    section_ids = set(section_hints or (
        candidate.section_id for candidate in understanding.candidates
    ))
    normalized_focus = understanding.normalized
    related_concepts = understanding.related_concepts
    label_refs = {
        f"{match.group(1)}{int(match.group(2))}.{int(match.group(3))}"
        for match in UNIT_HEADING.finditer(query)
    }
    expression = " OR ".join('"' + token.replace('"', "") + '"' for token in tokens)
    with closing(sqlite3.connect(index_path)) as db:
        db.row_factory = sqlite3.Row
        if related_concepts:
            for concept in related_concepts:
                for row in db.execute(
                    "SELECT DISTINCT section_id FROM units WHERE section LIKE ?",
                    ("%" + concept + "%",),
                ):
                    section_ids.add(int(row["section_id"]))
        lexical_candidates = list(db.execute(
            "SELECT u.*,bm25(units_fts) AS lexical_score "
            "FROM units_fts JOIN units u ON u.id=units_fts.id "
            "WHERE units_fts MATCH ? ORDER BY lexical_score LIMIT 50",
            (expression,),
        ))
        candidates_by_id = {row["id"]: row for row in lexical_candidates}
        dense_rank = {}
        model_name, vectors = _unit_vectors(
            str(index_path.resolve()), index_path.stat().st_mtime_ns
        )
        if model_name and vectors:
            try:
                query_vector = _unit(next(iter(_model(model_name).embed([query]))))
                dense = sorted(
                    (
                        (sum(a * b for a, b in zip(query_vector, vector)), unit_id)
                        for unit_id, vector, _ in vectors
                    ),
                    reverse=True,
                )[:40]
                dense_rank = {
                    unit_id: rank for rank, (_, unit_id) in enumerate(dense, 1)
                }
                dense_ids = list(dense_rank)
                placeholders = ",".join("?" for _ in dense_ids)
                for row in db.execute(
                    f"SELECT *,0.0 AS lexical_score FROM units WHERE id IN ({placeholders})",
                    tuple(dense_ids),
                ):
                    candidates_by_id.setdefault(row["id"], row)
            except (ImportError, OSError, ValueError):
                dense_rank = {}
        if label_refs:
            placeholders = ",".join("?" for _ in label_refs)
            for row in db.execute(
                f"SELECT *,0.0 AS lexical_score FROM units WHERE label IN ({placeholders})",
                tuple(sorted(label_refs)),
            ):
                candidates_by_id.setdefault(row["id"], row)
        if section_ids:
            placeholders = ",".join("?" for _ in section_ids)
            for row in db.execute(
                f"SELECT *,0.0 AS lexical_score FROM units "
                f"WHERE section_id IN ({placeholders})",
                tuple(sorted(section_ids)),
            ):
                candidates_by_id.setdefault(row["id"], row)
        candidates = list(candidates_by_id.values())
        query_terms = terms_for(expanded)
        ranked = []
        requested_kind = (
            "definition" if re.search(r"定义|什么是|是什么|称为|哪类|叫什么", query)
            else "theorem" if re.search(r"定理|条件|结论|性质", query)
            else ""
        )
        for order, row in enumerate(candidates):
            content_terms = terms_for(row["label"] + " " + row["section"] + " " + row["text"])
            overlap = query_terms & content_terms
            related_in_text = sum(
                concept in row["text"] for concept in related_concepts
            )
            related_in_section = sum(
                concept in row["section"] for concept in related_concepts
            )
            score = (
                max(0.0, 1.5 - order * 0.02)
                + sum(min(len(term), 4) for term in overlap) * 0.15
                + (4.0 if requested_kind and row["kind"] == requested_kind else 0)
                + (2.0 if row["section_id"] in section_ids else 0)
                + (5.0 if normalized_focus and normalized_focus in row["text"] else 0)
                + (0.3 if normalized_focus and normalized_focus in row["section"] else 0)
                + min(4.0, related_in_text * 1.2)
                + min(6.0, related_in_section * 3.0)
                + (20.0 if row["label"] in label_refs else 0)
                + (
                    max(0.0, 2.0 - (dense_rank[row["id"]] - 1) * 0.04)
                    if row["id"] in dense_rank else 0
                )
                - order * 0.001
            )
            ranked.append((score, row))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [
            TextbookChunk(
                source=row["source"],
                section=row["section"],
                text=row["text"],
                terms=terms_for(row["text"]),
                kind=row["kind"],
                section_id=row["section_id"],
                chunk_id=row["id"],
                parent_id=row["id"],
                chapter_id=row["chapter_id"],
                page=row["page"],
            )
            for _, row in ranked[:limit]
        ]
