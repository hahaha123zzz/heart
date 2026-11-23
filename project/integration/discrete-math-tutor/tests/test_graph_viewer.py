"""只读图谱的 PostgreSQL 输入与 API 契约；不依赖模型。"""

import json
import os

from fastapi.testclient import TestClient
import psycopg
import pytest

from graph_viewer import GraphView, create_app, digest
from tests.pg_support import temp_databases


@pytest.fixture
def candidate(tmp_path):
    with temp_databases() as env:
        os.environ.update(env)
        index = tmp_path / "index"
        index.mkdir()
        (index / "meta.json").write_text(json.dumps({"provider": "lightrag", "workspace": "ws"}), encoding="utf-8")
        url = env["POSTGRES_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
        with psycopg.connect(url) as conn:
            conn.execute("CREATE TABLE lightrag_graph_nodes (workspace TEXT, namespace TEXT, id TEXT, properties JSONB)")
            conn.execute("CREATE TABLE lightrag_graph_edges (workspace TEXT, namespace TEXT, src_id TEXT, tgt_id TEXT, properties JSONB)")
            conn.execute("CREATE TABLE lightrag_doc_chunks (id TEXT, workspace TEXT, content TEXT, file_path TEXT)")
            for node_id, props in (
                ("自变量", {"entity_type": "concept", "description": "候选摘要", "source_id": "chunk-1<SEP>chunk-1",
                         "file_path": "chapter_01.generated.pdf"}),
                ("实验", {"entity_type": "method"}),
                ("控制", {}),
            ):
                conn.execute("INSERT INTO lightrag_graph_nodes VALUES ('ws','chunk_entity_relation',%s,%s)", (node_id, json.dumps(props)))
            conn.execute("INSERT INTO lightrag_graph_edges VALUES ('ws','chunk_entity_relation','自变量','实验',%s)",
                         (json.dumps({"description": "关联，非先修"}),))
            conn.execute("INSERT INTO lightrag_graph_edges VALUES ('ws','chunk_entity_relation','自变量','控制',%s)", (json.dumps({}),))
            conn.execute("INSERT INTO lightrag_doc_chunks VALUES ('chunk-1','ws','原始检索片段','chapter_01.generated.pdf')")
        chapter = tmp_path / "input/chapters/chapter_01"
        chapter.mkdir(parents=True)
        pdf = chapter / "chapter_01.generated.pdf"
        pdf.write_bytes(b"%PDF-fixture")
        (tmp_path / "input/pdf_manifest.json").write_text(json.dumps([
            {"chapter_id": 1, "title": "实验心理学概论", "version": digest(pdf)}
        ]), encoding="utf-8")
        yield tmp_path


def test_search_and_bounded_neighborhood(candidate):
    view = GraphView(candidate)
    assert view.search("自变量")[0]["name"] == "自变量"
    neighborhood = view.neighborhood("自变量", 2)
    assert neighborhood["shown"] == 2 and neighborhood["total"] == 3
    assert neighborhood["truncated"]
    detail = view.detail("自变量", None)
    assert detail["descriptions"] == ["候选摘要"]
    assert detail["snippets"][0]["text"] == "原始检索片段"
    assert detail["source_count"] == 1
    assert detail["sources"][0]["available"]


def test_stale_graphml_file_does_not_override_postgres(candidate):
    (candidate / "index/workspace").mkdir()
    (candidate / "index/workspace/graph_chunk_entity_relation.graphml").write_text("stale", encoding="utf-8")
    assert GraphView(candidate).search("自变量")[0]["name"] == "自变量"


def test_api_and_source_invalidation(candidate):
    client = TestClient(create_app(candidate))
    assert client.get("/").status_code == 200
    assert client.get("/api/graph/summary").json()["read_only"] is True
    assert client.get("/api/graph/neighborhood", params={"name": "不存在"}).status_code == 404
    assert client.get("/api/graph/neighborhood?limit=999").status_code == 422
    assert client.get("/api/graph/detail").status_code == 400
    assert client.get("/api/graph/detail?edge=-1").status_code == 404
    assert client.get("/api/graph/detail?edge=0").json()["descriptions"] == ["关联，非先修"]
    assert client.get("/api/graph/pdf/chapter_01.generated.pdf").status_code == 200
    (candidate / "input/chapters/chapter_01/chapter_01.generated.pdf").write_bytes(b"changed")
    assert client.get("/api/graph/pdf/chapter_01.generated.pdf").status_code == 409
    assert not client.get("/api/graph/detail", params={"name": "自变量"}).json()["sources"][0]["available"]
    assert client.get("/api/graph/pdf/no-such.pdf").status_code == 404
