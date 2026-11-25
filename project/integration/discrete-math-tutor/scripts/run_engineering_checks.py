"""Run the release-critical Python test groups and record reproducible results."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / ".runtime/engineering-validation/latest.json"
GROUPS = {
    "retrieval_core": [
        "tests.test_local_rag",
        "tests.test_rag_upgrade",
    ],
    "query_semantic": [
        "tests.test_query_understanding",
        "tests.test_query_semantic_shadow",
        "tests.test_vector_retrieval_shadow",
        "tests.test_quoted_phrase_retrieval",
    ],
    "answer_quality": [
        "tests.test_answer_accuracy_eval",
        "tests.test_answer_accuracy_holdout",
        "tests.test_answer_ranking",
        "tests.test_mock_replies",
    ],
    "release_guard": [
        "tests.test_answer_release",
    ],
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    results = {}
    started_all = time.perf_counter()
    for name, modules in GROUPS.items():
        started = time.perf_counter()
        process = subprocess.run(
            [sys.executable, "-X", "utf8", "-m", "unittest", *modules, "-q"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        results[name] = {
            "modules": modules,
            "passed": process.returncode == 0,
            "returncode": process.returncode,
            "elapsed_seconds": round(time.perf_counter() - started, 2),
            "stdout_tail": process.stdout[-2000:],
            "stderr_tail": process.stderr[-2000:],
        }
    report = {
        "schema": "engineering-validation-v1",
        "created_at": datetime.now().astimezone().isoformat(),
        "python": sys.version,
        "passed": all(item["passed"] for item in results.values()),
        "elapsed_seconds": round(time.perf_counter() - started_all, 2),
        "groups": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({
        "passed": report["passed"],
        "elapsed_seconds": report["elapsed_seconds"],
        "groups": {
            name: {
                "passed": item["passed"],
                "elapsed_seconds": item["elapsed_seconds"],
            }
            for name, item in results.items()
        },
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
