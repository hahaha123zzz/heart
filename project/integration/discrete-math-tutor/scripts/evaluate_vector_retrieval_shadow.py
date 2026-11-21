"""Compare current retrieval with an isolated lexical-plus-vector index."""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

from knowledge.hybrid_retrieval import expand_section_context, retrieve_hybrid
from knowledge.query_semantic_shadow import SemanticSectionShadow
from knowledge.query_understanding import understand
from knowledge.textbook import load_textbook
from orchestrator import retrieve_course


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "tests/data/vector_retrieval_holdout_v1.jsonl"
DEFAULT_INDEX = ROOT / ".runtime/vector-retrieval-shadow-v1.sqlite3"
DEFAULT_OUTPUT = ROOT / ".runtime/vector-shadow/latest.json"
SEMANTIC_THRESHOLD = 0.51


def _norm(value: str) -> str:
    return "".join(str(value or "").split())


def _rank(sources, expected: str | None) -> int | None:
    if not expected:
        return None
    expected = _norm(expected)
    return next(
        (
            index
            for index, source in enumerate(sources, 1)
            if expected in _norm(
                source["title"] if isinstance(source, dict) else source.section
            )
        ),
        None,
    )


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return round(ordered[index], 2)


def _metrics(rows: list[dict], key: str, *, threshold: float | None = None) -> dict:
    in_scope = [row for row in rows if row["answerable"]]
    out_scope = [row for row in rows if not row["answerable"]]
    recall1 = 0
    recall3 = 0
    accepted_out_scope = 0
    abstained_in_scope = 0
    latencies = []
    for row in in_scope:
        item = row[key]
        accepted = True
        if threshold is not None:
            accepted = bool(item) and item[0]["score"] >= threshold
        recall1 += accepted and _rank(item, row.get("section")) == 1
        recall3 += bool(_rank(item, row.get("section")) and _rank(item, row.get("section")) <= 3)
        if not accepted:
            abstained_in_scope += 1
        latencies.append(row[f"{key}_ms"])
    for row in out_scope:
        item = row[key]
        accepted = bool(item)
        if threshold is not None:
            accepted = bool(item) and item[0]["score"] >= threshold
        accepted_out_scope += accepted
        latencies.append(row[f"{key}_ms"])
    rejection_precision = (
        (len(out_scope) - accepted_out_scope)
        / ((len(out_scope) - accepted_out_scope) + abstained_in_scope)
        if (len(out_scope) - accepted_out_scope) + abstained_in_scope
        else 0.0
    )
    rejection_recall = (
        (len(out_scope) - accepted_out_scope) / len(out_scope)
        if out_scope
        else 0.0
    )
    rejection_f1 = (
        2 * rejection_precision * rejection_recall
        / (rejection_precision + rejection_recall)
        if rejection_precision + rejection_recall
        else 0.0
    )
    return {
        "section_recall_at_1": round(recall1 / len(in_scope), 4) if in_scope else 0.0,
        "section_recall_at_3": round(recall3 / len(in_scope), 4) if in_scope else 0.0,
        "out_of_scope_rejection_precision": round(rejection_precision, 4),
        "out_of_scope_rejection_recall": round(rejection_recall, 4),
        "out_of_scope_rejection_f1": round(rejection_f1, 4),
        "latency_p50_ms": _percentile(latencies, 0.50),
        "latency_p95_ms": _percentile(latencies, 0.95),
    }


def _load(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def enable_gates(baseline: dict, vector: dict) -> dict:
    return {
        "recall_at_3_beats_current_by_0_05": (
            vector["section_recall_at_3"]
            >= baseline["section_recall_at_3"] + 0.05
        ),
        "out_of_scope_f1_at_least_0_85": (
            vector["out_of_scope_rejection_f1"] >= 0.85
        ),
        "p95_latency_at_most_2000_ms": vector["latency_p95_ms"] <= 2000,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model", default="BAAI/bge-small-zh-v1.5")
    parser.add_argument("--cache-dir")
    args = parser.parse_args()

    cases = _load(args.cases)
    chunks = load_textbook()
    semantic = SemanticSectionShadow(model_name=args.model, cache_dir=args.cache_dir)
    _ = retrieve_hybrid("集合", chunks, limit=1, index_path=args.index)
    _ = semantic.predict("集合", limit=1)
    rows = []
    for case in cases:
        started = time.perf_counter()
        baseline = retrieve_course(case["text"], chunks, limit=3)
        baseline_ms = (time.perf_counter() - started) * 1000

        started = time.perf_counter()
        query = understand(case["text"]).retrieval_query
        vector = retrieve_hybrid(query, chunks, limit=3, index_path=args.index)
        vector = expand_section_context(vector, index_path=args.index)
        vector_ms = (time.perf_counter() - started) * 1000

        started = time.perf_counter()
        semantic_items = semantic.predict(case["text"], limit=3)
        semantic_ms = (time.perf_counter() - started) * 1000
        rows.append({
            **case,
            "baseline": [
                {
                    "chapter_id": source.chapter_id,
                    "section_id": source.section_id,
                    "title": source.section,
                }
                for source in baseline
            ],
            "baseline_ms": round(baseline_ms, 2),
            "vector": [
                {
                    "chapter_id": source.chapter_id,
                    "section_id": source.section_id,
                    "title": source.section,
                }
                for source in vector
            ],
            "vector_ms": round(vector_ms, 2),
            "semantic": [
                {
                    "chapter_id": item.chapter_id,
                    "section_id": item.section_id,
                    "title": item.title,
                    "score": item.score,
                }
                for item in semantic_items
            ],
            "semantic_ms": round(semantic_ms, 2),
        })

    baseline_metrics = _metrics(rows, "baseline")
    vector_metrics = _metrics(rows, "vector")
    semantic_metrics = _metrics(rows, "semantic", threshold=SEMANTIC_THRESHOLD)
    gates = enable_gates(baseline_metrics, vector_metrics)
    report = {
        "schema": "vector-retrieval-shadow-v1",
        "model": args.model,
        "vector_index": str(args.index),
        "active_path_modified": False,
        "semantic_threshold": SEMANTIC_THRESHOLD,
        "baseline": baseline_metrics,
        "vector_hybrid": vector_metrics,
        "semantic_section": semantic_metrics,
        "gates": gates,
        "can_enable": all(gates.values()),
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({
        "baseline": baseline_metrics,
        "vector_hybrid": vector_metrics,
        "semantic_section": semantic_metrics,
        "gates": gates,
        "can_enable": report["can_enable"],
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
