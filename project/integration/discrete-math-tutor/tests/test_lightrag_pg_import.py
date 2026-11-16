"""LightRAG 候选索引一次性导入 PostgreSQL。"""
import json
import os

import networkx as nx

from tests.pg_support import temp_databases


def _matrix(rows, dim):
    import base64

    import numpy as np

    return base64.b64encode(np.zeros((rows, dim), dtype=np.float32).tobytes()).decode()


def build_fixture(root):
    index = root / "index"
    index.mkdir()
    (index / "meta.json").write_text(json.dumps({"provider": "lightrag", "workspace": "deeptutor_0123456789abcdef"}), encoding="utf-8")
    (index / "kv_store_full_docs.json").write_text(json.dumps({
        "doc-1": {"content": "正文", "file_path": "chapter_01.generated.pdf"},
    }), encoding="utf-8")
    (index / "kv_store_text_chunks.json").write_text(json.dumps({
        "doc-1-chunk-000": {"content": "正文", "full_doc_id": "doc-1", "chunk_order_index": 0,
                            "tokens": 2, "file_path": "chapter_01.generated.pdf"},
    }), encoding="utf-8")
    for name in ("full_entities", "full_relations", "entity_chunks", "relation_chunks", "llm_response_cache"):
        (index / f"kv_store_{name}.json").write_text("{}", encoding="utf-8")
    (index / "kv_store_doc_status.json").write_text(json.dumps({
        "doc-1": {"status": "processed", "content_summary": "正文", "content_length": 2,
                  "chunks_list": ["doc-1-chunk-000"],
                  "file_path": "chapter_01.generated.pdf", "chunks_count": 1},
    }), encoding="utf-8")
    (index / "vdb_chunks.json").write_text(json.dumps({
        "embedding_dim": 512,
        "data": [{"__id__": "doc-1-chunk-000", "content": "正文", "full_doc_id": "doc-1",
                  "chunk_order_index": 0, "tokens": 2, "file_path": "chapter_01.generated.pdf"}],
        "matrix": _matrix(1, 512),
    }), encoding="utf-8")
    (index / "vdb_entities.json").write_text(json.dumps({"embedding_dim": 512, "data": [], "matrix": ""}), encoding="utf-8")
    (index / "vdb_relationships.json").write_text(json.dumps({"embedding_dim": 512, "data": [], "matrix": ""}), encoding="utf-8")
    graph = nx.Graph()
    for name in ("实体A", "实体B"):
        graph.add_node(name, entity_id=name, entity_type="concept", description="描述",
                       source_id="doc-1-chunk-000", file_path="chapter_01.generated.pdf")
    graph.add_edge("实体A", "实体B", weight="1.0", description="关系", keywords="关键词",
                   source_id="doc-1-chunk-000", file_path="chapter_01.generated.pdf")
    nx.write_graphml(graph, index / "graph_chunk_entity_relation.graphml")


def test_import_is_idempotent(tmp_path):
    build_fixture(tmp_path)
    with temp_databases() as env:
        os.environ.update(env)
        os.environ["LIGHTRAG_QUERY_ENV_FILE"] = ""
        from scripts.import_lightrag_candidate_to_pg import import_candidate

        first = import_candidate(tmp_path)
        second = import_candidate(tmp_path)
        assert first["counts"] == second["counts"]
        assert first["counts"]["LIGHTRAG_DOC_CHUNKS"] == 1
        assert first["counts"]["LIGHTRAG_VDB_CHUNKS"] == 1
        assert first["counts"]["LIGHTRAG_DOC_STATUS"] == 1
