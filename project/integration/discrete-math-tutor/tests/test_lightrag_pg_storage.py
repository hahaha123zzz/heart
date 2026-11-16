"""LightRAG 只使用 PostgreSQL 存储。"""
import os

from tests.pg_support import temp_databases


def test_build_rag_uses_postgres_storages(tmp_path):
    with temp_databases() as env:
        os.environ.update(env)
        os.environ["LIGHTRAG_QUERY_ENV_FILE"] = ""
        from knowledge.lightrag.engine import build_rag

        rag = build_rag(tmp_path, query_only=True)
        assert (rag.kv_storage, rag.vector_storage, rag.graph_storage, rag.doc_status_storage) == (
            "PGKVStorage", "PGVectorStorage", "PGTableGraphStorage", "PGDocStatusStorage")
