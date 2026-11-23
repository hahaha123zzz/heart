"""LightRAG 文件后端与 PostgreSQL 后端的检索对照门禁。

门禁时关闭 PostgreSQL 索引扫描，要求两边命中集合一致；运行阶段仍用 HNSW。
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

os.environ["LIGHTRAG_QUERY_ENV_FILE"] = ""

CASES = ROOT / "tests/data/native_lightrag_latency_cases.json"


def compare_sets(file_ids, pg_ids):
    return {"file_ids": sorted(file_ids), "pg_ids": sorted(pg_ids), "equal": set(file_ids) == set(pg_ids)}


def _ids(data, key):
    return [str(row.get("chunk_id") or row.get("id") or "") for row in (data.get(key) or [])]


def _entity_terms(workspace: str) -> tuple[str, ...]:
    from knowledge.lightrag import storage

    with storage._pg_connect() as conn:
        rows = conn.execute(
            "SELECT id FROM lightrag_graph_nodes WHERE workspace = %s", (workspace,)
        ).fetchall()
    names = {row[0] for row in rows if isinstance(row[0], str) and 2 <= len(row[0]) <= 80}
    return tuple(sorted(names, key=lambda value: (-len(value), value)))


def _keywords(question: str, terms) -> tuple[str, ...]:
    text = " ".join(question.split()).casefold()
    found = []
    for term in terms:
        if term.casefold() in text and not any(term.casefold() in old.casefold() for old in found):
            found.append(term)
            if len(found) == 8:
                break
    return tuple(found)


def _file_rag(index: Path, workspace: str, embedding):
    from lightrag import LightRAG

    from knowledge.lightrag.config import (
        HostModel,
        Metrics,
        build_embedding_func,
        build_llm_model_func,
        constructor_kwargs_from_settings,
    )
    from llm.client import LLMClient

    model = HostModel(LLMClient(), Metrics())
    return LightRAG(
        working_dir=str(index),
        workspace=workspace,
        kv_storage="JsonKVStorage",
        vector_storage="NanoVectorDBStorage",
        graph_storage="NetworkXStorage",
        doc_status_storage="JsonDocStatusStorage",
        llm_model_func=build_llm_model_func(llm_config=model),
        embedding_func=build_embedding_func(embedding_config=embedding),
        auto_manage_storages_states=False,
        **constructor_kwargs_from_settings(),
    )


async def _query(rag, question: str, mode: str, keywords) -> dict:
    from lightrag import QueryParam

    from knowledge.lightrag.config import query_kwargs_from_settings

    param = QueryParam(mode=mode, stream=False, include_references=True, **query_kwargs_from_settings())
    if keywords:
        param.hl_keywords = list(keywords)
        param.ll_keywords = list(keywords)
    result = await rag.aquery_data(question, param=param)
    if result.get("status") != "success":
        return {}
    return result.get("data") or {}


def _set_exact_scan(enabled: bool) -> None:
    from knowledge.lightrag import storage

    with storage._pg_connect() as conn:
        dbname = conn.info.dbname
        indexscan = "off" if enabled else "on"
        conn.execute(f'ALTER DATABASE "{dbname}" SET enable_indexscan = {indexscan}')
        conn.execute(f'ALTER DATABASE "{dbname}" SET enable_seqscan = on')


def _bind_local_embedder() -> None:
    """离线加载已缓存 bge；fastembed 0.8 的 HF 缓存解析在本机不可用。"""
    import glob

    from fastembed import TextEmbedding

    import knowledge.hybrid_retrieval as hybrid

    cache = os.environ.get("FASTEMBED_CACHE_PATH")
    snapshot = os.environ.get("LIGHTRAG_EMBED_SNAPSHOT", "")
    if not snapshot:
        snapshots = glob.glob(os.path.join(cache or "", "models--Qdrant--bge-small-zh-v1.5", "snapshots", "*"))
        snapshot = snapshots[0] if snapshots else ""
    if not snapshot:
        return

    def factory(model_name, device=None):
        return TextEmbedding(model_name=model_name, specific_model_path=snapshot)

    hybrid._embedder_on_device = factory


async def run_gate(candidate: Path, *, modes=("naive", "hybrid"), report_dir: Path | None = None) -> dict:
    _bind_local_embedder()
    from knowledge.lightrag import storage
    from knowledge.lightrag.config import HostEmbedding, query_kwargs_from_settings  # noqa: F401
    from knowledge.lightrag.engine import build_rag, finalize, initialize

    index = Path(candidate) / "index"
    workspace = storage._workspace(index)
    embedding = HostEmbedding()
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    terms = _entity_terms(workspace)

    _set_exact_scan(True)
    pg = build_rag(index, query_only=True, embedding_config=embedding)
    file_rag = _file_rag(index, workspace, embedding)
    try:
        await initialize(pg)
        await initialize(file_rag)
        results = []
        for case in cases:
            question = case["question"]
            keywords = _keywords(question, terms) or (question,)
            for mode in modes:
                file_data = await _query(file_rag, question, mode, keywords)
                pg_data = await _query(pg, question, mode, keywords)
                keys = ("chunks",) if mode == "naive" else ("chunks", "entities", "relationships")
                comparisons = {key: compare_sets(_ids(file_data, key), _ids(pg_data, key)) for key in keys}
                results.append({
                    "id": case["id"], "mode": mode, "keyword_count": len(keywords),
                    "equal": all(item["equal"] for item in comparisons.values()),
                    "comparisons": comparisons,
                })
        report = {"candidate": str(candidate), "workspace": workspace,
                  "created_at": datetime.now().isoformat(timespec="seconds"), "results": results,
                  "equal": all(item["equal"] for item in results)}
        if report_dir is not None:
            report_dir.mkdir(parents=True, exist_ok=True)
            (report_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report
    finally:
        try:
            await finalize(file_rag, cancel_pending=True)
        finally:
            try:
                await finalize(pg, cancel_pending=True)
            finally:
                _set_exact_scan(False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--report-dir", default=None)
    args = parser.parse_args()
    report = asyncio.run(run_gate(Path(args.candidate), report_dir=Path(args.report_dir) if args.report_dir else None))
    print(json.dumps({"equal": report["equal"], "results": [
        {"id": item["id"], "mode": item["mode"], "equal": item["equal"]} for item in report["results"]]}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["equal"] else 1)


if __name__ == "__main__":
    main()
