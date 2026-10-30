"""只读图谱的输入边界与 API 契约；不依赖模型、正式数据库或候选。"""

import json

from fastapi.testclient import TestClient
import pytest

from graph_viewer import GraphView, create_app, digest


@pytest.fixture
def candidate(tmp_path):
    index = tmp_path / "index/workspace"
    index.mkdir(parents=True)
    graph = index / "graph_chunk_entity_relation.graphml"
    graph.write_text('''<graphml xmlns="http://graphml.graphdrawing.org/xmlns">
      <key id="type" for="node" attr.name="entity_type" attr.type="string"/>
      <key id="desc" for="all" attr.name="description" attr.type="string"/>
      <key id="src" for="all" attr.name="source_id" attr.type="string"/>
      <key id="file" for="all" attr.name="file_path" attr.type="string"/>
      <graph edgedefault="undirected">
      <node id="自变量"><data key="type">concept</data><data key="desc">候选摘要</data>
      <data key="src">chunk-1&lt;SEP&gt;chunk-1</data><data key="file">chapter_01.generated.pdf</data></node>
      <node id="实验"><data key="type">method</data></node><node id="控制"/>
      <edge source="自变量" target="实验"><data key="desc">关联，非先修</data></edge>
      <edge source="自变量" target="控制"/>
      </graph></graphml>''', encoding="utf-8")
    chunks = index / "kv_store_text_chunks.json"
    chunks.write_text(json.dumps({"chunk-1": {"content": "原始检索片段", "file_path": "chapter_01.generated.pdf"}}), encoding="utf-8")
    (tmp_path / "index_files.json").write_text(json.dumps({
        "workspace/" + f.name: digest(f) for f in (graph, chunks)
    }), encoding="utf-8")
    chapter = tmp_path / "input/chapters/chapter_01"
    chapter.mkdir(parents=True)
    pdf = chapter / "chapter_01.generated.pdf"
    pdf.write_bytes(b"%PDF-fixture")
    (tmp_path / "input/pdf_manifest.json").write_text(json.dumps([
        {"chapter_id": 1, "title": "实验心理学概论", "version": digest(pdf)}
    ]), encoding="utf-8")
    return tmp_path


def test_search_and_bounded_neighborhood(candidate):
    view = GraphView(candidate)
    assert view.search("自变量")[0]["name"] == "自变量"
    neighborhood = view.neighborhood("自变量", 2)
    assert neighborhood["shown"] == 2 and neighborhood["total"] == 3
    assert neighborhood["truncated"]
    nodes = {e["data"]["id"] for e in neighborhood["elements"] if "source" not in e["data"]}
    assert all(e["data"]["source"] in nodes and e["data"]["target"] in nodes
               for e in neighborhood["elements"] if "source" in e["data"])
    detail = view.detail("自变量", None)
    assert detail["descriptions"] == ["候选摘要"]
    assert detail["snippets"][0]["text"] == "原始检索片段"
    assert detail["source_count"] == 1
    assert detail["sources"][0]["available"]


def test_reject_modified_graph_and_escaping_path(candidate):
    graph = candidate / "index/workspace/graph_chunk_entity_relation.graphml"
    graph.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="版本"):
        GraphView(candidate)
    manifest = {"../../outside/graph_chunk_entity_relation.graphml": "x"}
    (candidate / "index_files.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RuntimeError):
        GraphView(candidate)


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
