"""Assess answer-quality metrics and open or close a release circuit."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from knowledge.answer_release import CIRCUIT_STATE, MANIFEST, verify


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / ".runtime/answer-release/latest-health.json"


def metrics_from_reports(paths: list[Path]) -> dict:
    rows = []
    first_token_values = []
    for path in paths:
        report = json.loads(path.read_text(encoding="utf-8"))
        rows.extend(report.get("rows") or ())
        value = report.get("first_token_p95_ms")
        if value is not None:
            first_token_values.append(float(value))
    in_scope = [row for row in rows if not row.get("expect_refusal")]
    out_scope = [row for row in rows if row.get("expect_refusal")]
    unsupported = sum(bool(row.get("unsupported_answer")) for row in in_scope)
    false_recall = sum(bool(row.get("status") == "answered") for row in out_scope)
    return {
        "samples": len(rows),
        "in_scope_samples": len(in_scope),
        "out_of_scope_samples": len(out_scope),
        "unsupported_citation_rate": (
            round(unsupported / len(in_scope), 4) if in_scope else None
        ),
        "out_of_scope_false_recall_rate": (
            round(false_recall / len(out_scope), 4) if out_scope else None
        ),
        "first_token_p95_ms": (
            round(max(first_token_values), 2) if first_token_values else None
        ),
    }


def assess_metrics(metrics: dict, thresholds: dict) -> dict:
    if metrics["samples"] < thresholds["minimum_samples"]:
        return {"ready": False, "healthy": None, "reasons": ["样本不足"]}
    reasons = []
    unsupported = metrics.get("unsupported_citation_rate")
    if (unsupported is not None
            and unsupported > thresholds["maximum_unsupported_citation_rate"]):
        reasons.append("无依据回答率超限")
    false_recall = metrics.get("out_of_scope_false_recall_rate")
    if (false_recall is not None
            and false_recall > thresholds["maximum_out_of_scope_false_recall_rate"]):
        reasons.append("教材外误召回率超限")
    latency = metrics.get("first_token_p95_ms")
    if (latency is not None
            and latency > thresholds["maximum_first_token_p95_ms"]):
        reasons.append("首字延迟 P95 超限")
    return {"ready": True, "healthy": not reasons, "reasons": reasons}


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def update_circuit(feature: str, *, open_feature: bool, path: Path) -> dict:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    features = set(state.get("features") or ())
    if open_feature:
        features.add(feature)
    else:
        features.discard(feature)
    value = {
        "global": bool(state.get("global", False)),
        "features": sorted(features),
        "updated_at": datetime.now().astimezone().isoformat(),
    }
    _write_json(path, value)
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feature", default="query_understanding")
    parser.add_argument("--report", type=Path, action="append", required=True)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--circuit", type=Path, default=CIRCUIT_STATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    release = verify(args.manifest)
    if release["ok"]:
        thresholds = release["manifest"]["thresholds"]
        metrics = metrics_from_reports(args.report)
        assessment = assess_metrics(metrics, thresholds)
    else:
        thresholds = {}
        metrics = {}
        assessment = {"ready": True, "healthy": False, "reasons": release["gaps"]}
    state = update_circuit(
        args.feature,
        open_feature=assessment["healthy"] is False,
        path=args.circuit,
    )
    report = {
        "schema": "answer-release-health-v1",
        "created_at": datetime.now().astimezone().isoformat(),
        "feature": args.feature,
        "release_id": release.get("release_id", ""),
        "manifest_ok": release["ok"],
        "metrics": metrics,
        "thresholds": thresholds,
        "assessment": assessment,
        "circuit": state,
    }
    _write_json(args.output, report)
    print(json.dumps({
        "release_id": report["release_id"],
        "manifest_ok": report["manifest_ok"],
        "metrics": metrics,
        "assessment": assessment,
        "circuit": state,
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
    return 0 if assessment["healthy"] is not False else 1


if __name__ == "__main__":
    raise SystemExit(main())
