"""保存召回候选、重排评分和证据门槛，帮助定位检索损失。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from pathlib import Path

from knowledge.hybrid_retrieval import INDEX, retrieve_hybrid
from knowledge.textbook import load_textbook
from scripts.eval_rag_holdout import _judge


def diagnose(cases_path: Path) -> dict:
    raw = cases_path.read_bytes()
    cases = json.loads(raw)
    chunks = load_textbook()
    rows = []
    with sqlite3.connect(INDEX) as db:
        for case in cases:
            trace = {}
            hits = retrieve_hybrid(case["question"], chunks, limit=3, trace=trace)
            wanted = case.get("sections") or [case.get("section", "")]
            def covers(ids):
                labels = [db.execute("SELECT chapter_id,section FROM chunks WHERE id=?", (key,)).fetchone()
                          for key in ids]
                return all(any(label and label[0] == case["chapter"] and section in label[1]
                               for label in labels) for section in wanted)
            candidate_ids = [item["id"] for item in trace.get("candidates", [])]
            rows.append({"id": case["id"], "candidate_covers_section": (
                covers(candidate_ids) if case["chapter"] else None),
                **_judge(case, hits), "trace": trace})
    return {"cases_sha256": hashlib.sha256(raw).hexdigest(), "rows": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reranker", default="")
    args = parser.parse_args()
    os.environ["RAG_RERANK_MODEL"] = args.reranker
    result = diagnose(args.cases)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    positive = [row for row in result["rows"] if row["hit_at_2"] is not None]
    print("候选覆盖小节", sum(row["candidate_covers_section"] for row in positive), "/", len(positive))
    print("Hit@2", sum(row["hit_at_2"] for row in positive), "/", len(positive))
    for row in result["rows"]:
        if row["hit_at_2"] is False or row["trace"].get("reranker_error"):
            print(row["id"], row["candidate_covers_section"], row["trace"].get("rejection"),
                  row["trace"].get("reranker_error"))
