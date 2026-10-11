"""冻结题集上的教材检索评估；只读索引，不修改检索规则。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from collections import defaultdict
from pathlib import Path

from knowledge.hybrid_retrieval import INDEX, retrieve_hybrid
from knowledge.textbook import load_textbook, retrieve

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "tests" / "data" / "rag_holdout.json"
OUTPUT = ROOT / "artifacts" / "rag_holdout_results.json"


def _judge(case: dict, hits: list) -> dict:
    if case["chapter"] is None:
        return {"has_evidence": bool(hits), "hit_at_2": None, "hit_at_3": None}
    wanted = case.get("sections") or [case["section"]]

    def chapter_of(hit) -> int | None:
        if hit.chapter_id is not None:
            return hit.chapter_id
        match = re.search(r"第\s*(\d+)\s*章", hit.source)
        return int(match.group(1)) if match else None

    def covered(prefix: list) -> bool:
        return all(any(chapter_of(hit) == case["chapter"] and section in hit.section
                       and ("kind" not in case or hit.kind == case["kind"])
                       for hit in prefix) for section in wanted)

    return {"has_evidence": bool(hits), "hit_at_2": covered(hits[:2]),
            "hit_at_3": covered(hits[:3])}


def evaluate(cases_path: Path = CASES, *, with_trace: bool = False) -> dict:
    raw = cases_path.read_bytes()
    cases = json.loads(raw.decode("utf-8"))
    chunks = load_textbook()
    report = {"index": str(INDEX), "index_exists": INDEX.exists(),
              "cases_file": str(cases_path), "cases_sha256": hashlib.sha256(raw).hexdigest(),
              "cases": len(cases), "rerank_model": os.environ.get("RAG_RERANK_MODEL", ""),
              "methods": {}}
    for name, method in (("baseline", retrieve), ("hybrid", retrieve_hybrid)):
        rows = []
        started = time.perf_counter()
        for case in cases:
            t0 = time.perf_counter()
            trace = {}
            hits = (method(case["question"], chunks, limit=3, trace=trace)
                    if name == "hybrid" and with_trace else method(case["question"], chunks, limit=3))
            rows.append({"id": case["id"], "question": case["question"], "category": case["category"],
                         "expected_chapter": case["chapter"],
                         "expected_sections": case.get("sections") or ([case["section"]] if case["chapter"] else []),
                         "expected_kind": case.get("kind"),
                         "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                         **_judge(case, hits), **({"trace": trace} if with_trace and name == "hybrid" else {}),
                         "hits": [{"chapter": (hit.chapter_id if hit.chapter_id is not None else
                                                (int(m.group(1)) if (m := re.search(r"第\s*(\d+)\s*章", hit.source)) else None)),
                                   "section": hit.section, "kind": hit.kind,
                                   "source": hit.source, "page": hit.page,
                                   "excerpt": hit.text[:220]}
                                  for hit in hits]})
        positive = [row for row in rows if row["expected_chapter"] is not None]
        negative = [row for row in rows if row["expected_chapter"] is None]
        by_category = defaultdict(lambda: {"total": 0, "hit_at_2": 0})
        for row in positive:
            stats = by_category[row["category"]]
            stats["total"] += 1
            stats["hit_at_2"] += int(row["hit_at_2"])
        report["methods"][name] = {
            "positive_total": len(positive),
            "hit_at_2": sum(row["hit_at_2"] for row in positive),
            "hit_at_3": sum(row["hit_at_3"] for row in positive),
            "out_of_scope_with_evidence": sum(row["has_evidence"] for row in negative),
            "out_of_scope_total": len(negative),
            "elapsed_seconds": round(time.perf_counter() - started, 2),
            "median_latency_ms": sorted(row["latency_ms"] for row in rows)[len(rows) // 2],
            "categories": dict(by_category), "rows": rows,
        }
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=CASES)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--reranker", default=None)
    parser.add_argument("--trace", action="store_true")
    args = parser.parse_args()
    if args.reranker is not None:
        os.environ["RAG_RERANK_MODEL"] = args.reranker
    result = evaluate(args.cases, with_trace=args.trace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for name, data in result["methods"].items():
        print(f"{name}: Hit@2 {data['hit_at_2']}/{data['positive_total']}, "
              f"Hit@3 {data['hit_at_3']}/{data['positive_total']}, "
              f"教材外仍给出处 {data['out_of_scope_with_evidence']}/{data['out_of_scope_total']}, "
              f"中位延迟 {data['median_latency_ms']}ms, 总计 {data['elapsed_seconds']}s")
        for row in data["rows"]:
            if row["hit_at_2"] is False or (row["expected_chapter"] is None and row["has_evidence"]):
                print(f"  {row['id']} {row['question']} => "
                      + "; ".join(f"{hit['chapter']}:{hit['section']}/{hit['kind']}" for hit in row["hits"]))
    print(f"完整结果：{args.output}")
