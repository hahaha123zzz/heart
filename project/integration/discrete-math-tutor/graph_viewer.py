"""独立、只读的候选图谱浏览器；不加载助教、模型、数据库或 LightRAG SDK。"""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from knowledge.lightrag.ingress import _contained_regular_file

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def parts(value: str) -> list[str]:
    return list(dict.fromkeys(v.strip() for v in value.split("<SEP>") if v.strip()))


class GraphView:
    def __init__(self, candidate: Path):
        self.root = candidate.resolve(strict=True)
        from knowledge.lightrag import storage

        self.workspace = storage._workspace(self.root / "index")
        with storage._pg_connect() as conn:
            node_rows = conn.execute(
                "SELECT id, properties FROM lightrag_graph_nodes WHERE workspace = %s",
                (self.workspace,),
            ).fetchall()
            edge_rows = conn.execute(
                "SELECT src_id, tgt_id, properties FROM lightrag_graph_edges WHERE workspace = %s",
                (self.workspace,),
            ).fetchall()
            chunk_rows = conn.execute(
                "SELECT id, content, file_path FROM lightrag_doc_chunks WHERE workspace = %s",
                (self.workspace,),
            ).fetchall()
        self.nodes = {node_id: dict(properties or {}) for node_id, properties in node_rows}
        self.edges = []
        self.adj = defaultdict(list)
        for source, target, properties in edge_rows:
            idx = len(self.edges)
            self.edges.append({**(properties or {}), "source": source, "target": target})
            self.adj[source].append(idx)
            if source != target:
                self.adj[target].append(idx)
        self.chunks = {chunk_id: {"content": content or "", "file_path": file_path or ""}
                       for chunk_id, content, file_path in chunk_rows}
        self.checked = {}
        self.graph_hash = hashlib.sha256(json.dumps(
            [sorted(self.nodes), sorted((e["source"], e["target"]) for e in self.edges)],
            ensure_ascii=False).encode()).hexdigest()
        self.pdfs = {}
        for entry in json.loads(self.file("input/pdf_manifest.json").read_text("utf-8")):
            chapter = int(entry["chapter_id"])
            name = f"chapter_{chapter:02d}.generated.pdf"
            self.pdfs[name] = (f"input/chapters/chapter_{chapter:02d}/{name}", entry)

    def file(self, relative: str) -> Path:
        return _contained_regular_file(self.root, self.root / relative, label="图谱浏览输入")

    def check(self, path: Path, expected: str):
        stat = path.stat()
        identity = (stat.st_mtime_ns, stat.st_size, expected)
        if self.checked.get(path) != identity:
            if digest(path) != expected:
                raise ValueError("文件版本与候选清单不一致，已停止读取")
            self.checked[path] = identity

    def pdf(self, name: str) -> Path:
        if name not in self.pdfs:
            raise KeyError(name)
        relative, entry = self.pdfs[name]
        path = self.file(relative)
        self.check(path, entry["version"])
        return path

    def node(self, name: str) -> dict:
        return {"data": {"id": name, "label": name, "type": self.nodes[name].get("entity_type", "unknown"),
                         "degree": len(self.adj[name])}}

    def neighborhood(self, name: str | None, limit: int = 60) -> dict:
        if name is not None and name not in self.nodes:
            raise KeyError(name)
        if name is None:
            selected = sorted(self.nodes, key=lambda n: (-len(self.adj[n]), n))[:limit]
            total = len(self.nodes)
        else:
            neighbors = set()
            for idx in self.adj[name]:
                edge = self.edges[idx]
                neighbors.update((edge["source"], edge["target"]))
            neighbors.discard(name)
            selected = [name] + sorted(neighbors, key=lambda n: (-len(self.adj[n]), n))[:limit - 1]
            total = len(neighbors) + 1
        chosen = set(selected)
        edges = [{"data": {"id": f"edge-{i}", "source": e["source"], "target": e["target"]}}
                 for i, e in enumerate(self.edges) if e["source"] in chosen and e["target"] in chosen]
        return {"elements": [self.node(n) for n in selected] + edges,
                "total": total, "shown": len(selected), "truncated": len(selected) < total}

    def search(self, query: str) -> list:
        names = [n for n in self.nodes if query.casefold() in n.casefold()]
        return [{"name": n, "type": self.nodes[n].get("entity_type"), "degree": len(self.adj[n])}
                for n in sorted(names, key=lambda n: (n != query, len(n), n))[:30]]

    def detail(self, name: str | None, edge: int | None) -> dict:
        if edge is not None:
            if not 0 <= edge < len(self.edges):
                raise KeyError(edge)
            record = self.edges[edge]
            title = record["source"] + " — " + record["target"]
        else:
            record = self.nodes[name]
            title = name
        snippets, sources = [], {}
        ids = parts(record.get("source_id", ""))
        # shortcut: 详情最多展示八个检索片段；需要逐条审计时使用来源 PDF。
        files = parts(record.get("file_path", ""))
        for chunk_id in ids[:8]:
            chunk = self.chunks.get(chunk_id)
            if chunk:
                snippets.append({"id": chunk_id, "text": chunk.get("content", "")[:5000],
                                 "file": chunk.get("file_path", "")})
                files.extend(parts(chunk.get("file_path", "")))
        for file in dict.fromkeys(files):
            if file in self.pdfs:
                _, entry = self.pdfs[file]
                try:
                    self.pdf(file)
                    available = True
                except (OSError, ValueError, RuntimeError):
                    available = False
                sources[file] = {"file": file, "title": entry["title"], "chapter": entry["chapter_id"],
                                 "version": entry["version"], "available": available}
        return {"title": title, "descriptions": parts(record.get("description", "")),
                "keywords": record.get("keywords", ""), "sources": list(sources.values()),
                "snippets": snippets, "source_count": len(ids)}


def create_app(candidate: Path) -> FastAPI:
    view = GraphView(candidate)
    app = FastAPI(title="候选知识图谱 · 只读浏览", docs_url=None, redoc_url=None)
    frontend = Path(__file__).parent / "frontend"
    app.mount("/assets", StaticFiles(directory=frontend / "knowledge-graph"), name="assets")
    app.mount("/vendor", StaticFiles(directory=frontend / "vendor/cytoscape"), name="vendor")

    @app.get("/")
    def page():
        return FileResponse(frontend / "knowledge-graph/index.html")

    @app.get("/api/graph/summary")
    def summary():
        return {"nodes": len(view.nodes), "edges": len(view.edges), "documents": len(view.pdfs),
                "graph_sha256": view.graph_hash, "status": "candidate", "read_only": True}

    @app.get("/api/graph/search")
    def search(q: str = Query(min_length=1, max_length=100)):
        return view.search(q.strip()) if q.strip() else []

    @app.get("/api/graph/neighborhood")
    def neighborhood(name: str | None = Query(default=None, max_length=1000),
                     limit: int = Query(default=60, ge=2, le=150)):
        try:
            return view.neighborhood(name, limit)
        except KeyError:
            raise HTTPException(404, "实体不存在")

    @app.get("/api/graph/detail")
    def detail(name: str | None = Query(default=None, max_length=1000), edge: int | None = None):
        if (name is None) == (edge is None):
            raise HTTPException(400, "请选择一个实体或一条关系")
        try:
            return view.detail(name, edge)
        except KeyError:
            raise HTTPException(404, "实体或关系不存在")

    @app.get("/api/graph/pdf/{name}")
    def pdf(name: str):
        try:
            return FileResponse(view.pdf(name), media_type="application/pdf")
        except KeyError:
            raise HTTPException(404, "教材不存在")
        except (OSError, ValueError, RuntimeError):
            raise HTTPException(409, "来源缺失或版本失效，不能打开")

    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    import uvicorn
    uvicorn.run(create_app(args.candidate), host="127.0.0.1", port=args.port)
