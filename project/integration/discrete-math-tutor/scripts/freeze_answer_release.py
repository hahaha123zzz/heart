"""Create a deterministic answer-quality release manifest from current files."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from knowledge.answer_release import expected_release_id, sha256_path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "knowledge/releases/query-accuracy-v1.json"
ARTIFACTS = (
    "knowledge/rag_index_v2.sqlite3",
    ".runtime/vector-retrieval-shadow-v1.sqlite3",
    "knowledge/answer_release.py",
    "knowledge/answer_ranking.py",
    "knowledge/grounded_citations.py",
    "knowledge/hybrid_retrieval.py",
    "knowledge/query_understanding.py",
    "knowledge/query_semantic_shadow.py",
    "orchestrator.py",
    "scripts/run_engineering_checks.py",
    "scripts/run_release_health.py",
    "scripts/measure_first_token.py",
    "tests/data/e2e_answer_accuracy_v1.json",
    "tests/data/e2e_answer_accuracy_holdout_v1.json",
    "tests/data/e2e_answer_accuracy_holdout_v2.json",
    "tests/data/semantic_query_annotations_v1.jsonl",
    "tests/data/vector_retrieval_holdout_v1.jsonl",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    manifest = {
        "schema": "answer-accuracy-release-v1",
        "created_at": datetime.now().astimezone().isoformat(),
        "source_commit": args.source_commit,
        "course_id": "discrete-math",
        "artifacts": [
            {"path": path, "sha256": sha256_path(ROOT / path)}
            for path in ARTIFACTS
        ],
        "features": {
            "query_understanding": {
                "mode": "shadow",
                "percent": 5,
                "test_accounts_active": True,
            },
            "semantic_section_resolver": {
                "mode": "shadow",
                "percent": 0,
                "test_accounts_active": False,
            },
            "vector_hybrid": {
                "mode": "off",
                "percent": 0,
                "test_accounts_active": False,
            },
        },
        "thresholds": {
            "minimum_samples": 20,
            "maximum_unsupported_citation_rate": 0.15,
            "maximum_out_of_scope_false_recall_rate": 0.10,
            "maximum_first_token_p95_ms": 3000,
        },
    }
    manifest["release_id"] = expected_release_id(manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({
        "release_id": manifest["release_id"],
        "artifacts": len(manifest["artifacts"]),
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
