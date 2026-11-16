"""LightRAG 就绪判断读取 PostgreSQL。"""
import json
import os

import psycopg

from tests.pg_support import temp_databases


def test_has_output_reads_doc_status_from_postgres(tmp_path):
    with temp_databases() as env:
        os.environ.update(env)
        url = env["POSTGRES_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
        with psycopg.connect(url) as conn:
            conn.execute(
                "CREATE TABLE lightrag_doc_status (workspace TEXT, id TEXT, content_summary TEXT, "
                "content_length INT, chunks_count INT, status TEXT, file_path TEXT, chunks_list JSONB, error_msg TEXT)"
            )
            conn.execute(
                "INSERT INTO lightrag_doc_status (workspace, id, status, chunks_list) "
                "VALUES ('ws', 'doc-1', 'processed', '[\"chunk-1\"]'::jsonb)"
            )
        (tmp_path / "meta.json").write_text(json.dumps({"workspace": "ws"}), encoding="utf-8")
        from knowledge.lightrag import storage

        assert storage.has_output(tmp_path) is True
