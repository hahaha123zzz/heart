"""把已构建的 LightRAG 候选索引导入 PostgreSQL。

一次性工具：不调用 LLM，不重新建图；保留原 doc_id/chunk_id/workspace 与向量。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TABLE_FILES = {
    "LIGHTRAG_DOC_FULL": ("full_docs", "kv_store_full_docs.json"),
    "LIGHTRAG_DOC_CHUNKS": ("text_chunks", "kv_store_text_chunks.json"),
    "LIGHTRAG_FULL_ENTITIES": ("full_entities", "kv_store_full_entities.json"),
    "LIGHTRAG_FULL_RELATIONS": ("full_relations", "kv_store_full_relations.json"),
    "LIGHTRAG_ENTITY_CHUNKS": ("entity_chunks", "kv_store_entity_chunks.json"),
    "LIGHTRAG_RELATION_CHUNKS": ("relation_chunks", "kv_store_relation_chunks.json"),
    "LIGHTRAG_LLM_CACHE": ("llm_response_cache", "kv_store_llm_response_cache.json"),
    "LIGHTRAG_DOC_STATUS": ("doc_status", "kv_store_doc_status.json"),
}


def _digest(path: Path) -> str:
    import hashlib

    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _vector(values) -> str:
    return "[" + ",".join(repr(float(value)) for value in values) + "]"


def _vectors(index: Path, filename: str):
    import base64

    import numpy as np

    payload = _read(index / filename)
    rows = payload.get("data") or []
    dim = int(payload.get("embedding_dim") or 0)
    raw = base64.b64decode(payload.get("matrix") or "")
    matrix = np.frombuffer(raw, dtype=np.float32)
    if not rows:
        return []
    if dim <= 0 or matrix.size != len(rows) * dim:
        raise ValueError(f"{filename} 向量矩阵与行数不一致")
    matrix = matrix.reshape(len(rows), dim)
    return list(zip(rows, matrix))


def _import_vectors(conn, workspace: str, index: Path) -> None:
    chunks = _vectors(index, "vdb_chunks.json")
    entities = _vectors(index, "vdb_entities.json")
    relationships = _vectors(index, "vdb_relationships.json")
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO lightrag_vdb_chunks (id, workspace, full_doc_id, chunk_order_index, tokens, content, content_vector, file_path) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s::vector,%s) "
            "ON CONFLICT (workspace,id) DO UPDATE SET content=EXCLUDED.content, content_vector=EXCLUDED.content_vector, "
            "full_doc_id=EXCLUDED.full_doc_id, chunk_order_index=EXCLUDED.chunk_order_index, tokens=EXCLUDED.tokens, file_path=EXCLUDED.file_path",
            [
                (
                    row["__id__"], workspace, row.get("full_doc_id"), row.get("chunk_order_index"),
                    row.get("tokens"), row.get("content"), _vector(vector), row.get("file_path"),
                )
                for row, vector in chunks
            ],
        )
        cur.executemany(
            "INSERT INTO lightrag_vdb_entity (id, workspace, entity_name, content, content_vector, chunk_ids, file_path) "
            "VALUES (%s,%s,%s,%s,%s::vector,%s,%s) "
            "ON CONFLICT (workspace,id) DO UPDATE SET entity_name=EXCLUDED.entity_name, content=EXCLUDED.content, "
            "content_vector=EXCLUDED.content_vector, chunk_ids=EXCLUDED.chunk_ids, file_path=EXCLUDED.file_path",
            [
                (
                    row["__id__"], workspace, row.get("entity_name"), row.get("content"), _vector(vector),
                    [part for part in str(row.get("source_id") or "").split("<SEP>") if part], row.get("file_path"),
                )
                for row, vector in entities
            ],
        )
        cur.executemany(
            "INSERT INTO lightrag_vdb_relation (id, workspace, source_id, target_id, content, content_vector, chunk_ids, file_path) "
            "VALUES (%s,%s,%s,%s,%s,%s::vector,%s,%s) "
            "ON CONFLICT (workspace,id) DO UPDATE SET source_id=EXCLUDED.source_id, target_id=EXCLUDED.target_id, "
            "content=EXCLUDED.content, content_vector=EXCLUDED.content_vector, chunk_ids=EXCLUDED.chunk_ids, file_path=EXCLUDED.file_path",
            [
                (
                    row["__id__"], workspace, row.get("src_id"), row.get("tgt_id"), row.get("content"),
                    _vector(vector),
                    [part for part in str(row.get("source_id") or "").split("<SEP>") if part], row.get("file_path"),
                )
                for row, vector in relationships
            ],
        )


async def _import(candidate: Path) -> dict:
    import os

    os.environ["LIGHTRAG_QUERY_ENV_FILE"] = ""
    import networkx as nx

    from knowledge.lightrag.config import HostEmbedding
    from knowledge.lightrag.engine import build_rag, finalize, initialize
    from knowledge.lightrag import storage

    index = candidate / "index"
    rag = build_rag(index, query_only=True, embedding_config=HostEmbedding())
    await initialize(rag)
    try:
        workspace = storage._workspace(index)
        store_root = storage._store_root(index)
        for _table, (attribute, filename) in TABLE_FILES.items():
            data = _read(store_root / filename)
            if data:
                await getattr(rag, attribute).upsert(data)
        with storage._pg_connect() as conn:
            _import_vectors(conn, workspace, store_root)
        graph = nx.read_graphml(store_root / "graph_chunk_entity_relation.graphml")
        store = rag.chunk_entity_relation_graph
        for node_id, node_data in graph.nodes(data=True):
            await store.upsert_node(node_id, dict(node_data))
        for source, target, edge_data in graph.edges(data=True):
            await store.upsert_edge(source, target, dict(edge_data))
        with storage._pg_connect() as conn:
            entries = {name: storage.table_fingerprint(conn, workspace, name) for name in storage.INDEX_TABLES}
        from knowledge.lightrag.file_io import atomic_write_json

        atomic_write_json(candidate / "index_files.json", entries)
        storage.write_manifest(index, entries, source_signature=_digest(candidate / "index_files.json"))
        return {"counts": {name: entry["row_count"] for name, entry in entries.items()}, "manifest": entries}
    finally:
        await finalize(rag, cancel_pending=True)


def import_candidate(candidate: Path, *, dry_run: bool = False) -> dict:
    if dry_run:
        return {"counts": {}, "manifest": {}}
    return asyncio.run(_import(Path(candidate)))


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a built LightRAG candidate into PostgreSQL")
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(import_candidate(Path(args.candidate), dry_run=args.dry_run), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
