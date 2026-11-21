"""Measure effective first answer-token latency through the streaming API."""

from __future__ import annotations

import argparse
import json
import math
import time
import uuid
from datetime import datetime
from pathlib import Path

import httpx


QUESTIONS = [
    "集合的并集怎样定义？",
    "图中的顶点度数是什么？",
    "什么是等价关系？",
    "函数复合的次序怎样确定？",
    "鸽笼原理说明什么？",
]
DEFAULT_OUTPUT = Path(".runtime/answer-release/first-token-latency.json")


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
    return round(ordered[index], 2)


def measure(base_url: str, question: str, student_id: str) -> dict:
    started = time.monotonic()
    first_answer = None
    answer_status = None
    event_name = ""
    with httpx.Client(trust_env=False, timeout=180) as client:
        with client.stream(
            "POST",
            base_url.rstrip("/") + "/api/chat/stream",
            json={
                "student_id": student_id,
                "message": question,
                "account_type": "test",
                "session_id": "first-token-" + uuid.uuid4().hex,
            },
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line.startswith("event:"):
                    event_name = line[6:].strip()
                    continue
                if not line.startswith("data:"):
                    continue
                data = json.loads(line[5:])
                if (event_name == "answer_delta" and first_answer is None
                        and data.get("text")
                        and data.get("role", "answer") == "answer"):
                    first_answer = round((time.monotonic() - started) * 1000, 2)
                if (event_name == "answer" and first_answer is None
                        and any(data.get(key) for key in ("reply", "text", "content"))):
                    first_answer = round((time.monotonic() - started) * 1000, 2)
                if event_name == "done":
                    answer_status = data.get("answer_status")
                    if first_answer is None and data.get("reply"):
                        first_answer = round((time.monotonic() - started) * 1000, 2)
    return {
        "question": question,
        "first_answer_delta_ms": first_answer,
        "answer_status": answer_status,
        "complete_ms": round((time.monotonic() - started) * 1000, 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--repeat", type=int, default=2)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    questions = QUESTIONS
    if args.cases:
        cases = json.loads(args.cases.read_text(encoding="utf-8"))
        questions = [item["message"] if isinstance(item, dict) else str(item) for item in cases]
    if args.repeat < 1:
        parser.error("repeat must be positive")

    student_id = "first-token-" + uuid.uuid4().hex[:20]
    with httpx.Client(trust_env=False, timeout=30) as client:
        client.post(
            args.base_url.rstrip("/") + "/api/accounts/test",
            json={"student_id": student_id, "ttl_hours": 1},
        ).raise_for_status()
    rows = []
    try:
        for _ in range(args.repeat):
            for question in questions:
                rows.append(measure(args.base_url, question, student_id))
    finally:
        with httpx.Client(trust_env=False, timeout=30) as client:
            client.delete(args.base_url.rstrip("/") + f"/api/accounts/test/{student_id}")

    values = [
        row["first_answer_delta_ms"]
        for row in rows
        if row["first_answer_delta_ms"] is not None
    ]
    report = {
        "schema": "first-token-latency-v1",
        "created_at": datetime.now().astimezone().isoformat(),
        "samples": len(rows),
        "successful_samples": len(values),
        "first_token_p50_ms": percentile(values, 0.50),
        "first_token_p95_ms": percentile(values, 0.95),
        "metric_source": "answer_delta_or_first_visible_body",
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({
        key: report[key]
        for key in (
            "samples",
            "successful_samples",
            "first_token_p50_ms",
            "first_token_p95_ms",
        )
    } | {"output": str(args.output)}, ensure_ascii=False, indent=2))
    return 0 if values else 1


if __name__ == "__main__":
    raise SystemExit(main())
