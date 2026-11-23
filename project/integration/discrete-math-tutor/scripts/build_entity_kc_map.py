"""实体 → 知识点映射（基于 LightRAG chunk heading 与教材节标题精确匹配）。

产物：knowledge/courses/experimental-psychology-3/kc_entity_map.json
依据：chunk.heading 归一化后等于某节标题；不按名称相似度猜。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import psycopg

COURSE = Path(__file__).resolve().parents[1] / "knowledge" / "courses" / "experimental-psychology-3"
OUT = COURSE / "kc_entity_map.json"
DSN = "postgresql://heart:heart_pg_admin@127.0.0.1:5432/heart_rag"
WORKSPACE = "deeptutor_426733019d24d665"
SECTION_PREFIX = re.compile(r"^第[一二三四五六七八九十百]+节\s*")


def normalize(text: str) -> str:
    value = SECTION_PREFIX.sub("", str(text or "").replace("\u3000", " "))
    return re.sub(r"\s+", "", value).strip()


def main() -> None:
    registry = json.loads((COURSE / "kc_registry_full.json").read_text(encoding="utf-8"))
    by_name: dict[str, str] = {}
    for component in registry["knowledge_components"]:
        by_name[normalize(component["name"])] = component["id"]

    with psycopg.connect(DSN) as conn:
        chunks = conn.execute(
            "select id, heading->>'heading', heading->'parent_headings' "
            "from lightrag_doc_chunks where workspace=%s", (WORKSPACE,)).fetchall()
        chunk_kc: dict[str, str] = {}
        unmatched_headings: set[str] = set()
        for chunk_id, heading, parents in chunks:
            candidates = [heading]
            if parents:
                candidates.extend(str(p) for p in parents)
            for candidate in candidates:
                kc = by_name.get(normalize(candidate))
                if kc:
                    chunk_kc[chunk_id] = kc
                    break
            else:
                if heading:
                    unmatched_headings.add(normalize(heading))

        rows = conn.execute(
            "select id, chunk_ids from lightrag_entity_chunks where workspace=%s",
            (WORKSPACE,)).fetchall()
        mapping = []
        unmapped = 0
        for entity_id, chunk_ids in rows:
            if isinstance(chunk_ids, str):
                ids = [part for part in chunk_ids.split("<SEP>") if part]
            else:
                ids = [str(part) for part in (chunk_ids or [])]
            kcs = sorted({chunk_kc[c] for c in ids if c in chunk_kc})
            if kcs:
                mapping.append({"entity": entity_id, "kc_ids": kcs,
                                "basis": "chunk_heading"})
            else:
                unmapped += 1

    payload = {
        "schema": "kc-entity-map-v1",
        "course_id": registry["course_id"],
        "workspace": WORKSPACE,
        "basis": "chunk.heading 与 kc name 精确匹配（不用相似度）",
        "mapped_entities": len(mapping),
        "unmapped_entities": unmapped,
        "chunks_mapped": len(chunk_kc),
        "unmatched_headings": len(unmatched_headings),
        "mappings": mapping,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"file={OUT}")
    print(f"mapped={len(mapping)} unmapped={unmapped} chunks_mapped={len(chunk_kc)} "
          f"unmatched_headings={len(unmatched_headings)}")
    for item in mapping[:5]:
        print(" ", item)


if __name__ == "__main__":
    main()
