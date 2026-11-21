"""Compare lexical query understanding with an offline semantic shadow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from knowledge.query_semantic_shadow import SemanticSectionShadow
from knowledge.query_understanding import rank_sections


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "tests/data/semantic_query_annotations_v1.jsonl"
DEFAULT_OUTPUT = ROOT / ".runtime/semantic-shadow/latest.json"


def _normalized(value: str) -> str:
    return "".join(str(value or "").split())


def _section_rank(candidates, expected: str) -> int | None:
    expected = _normalized(expected)
    return next(
        (
            index
            for index, candidate in enumerate(candidates, 1)
            if expected in _normalized(
                candidate["title"] if isinstance(candidate, dict) else candidate.title
            )
        ),
        None,
    )


def _safe_ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def evaluate_rows(rows: list[dict], threshold: float) -> dict:
    in_scope = [row for row in rows if row["answerable"]]
    out_scope = [row for row in rows if not row["answerable"]]
    concept_tp = 0
    concept_fp = 0
    concept_fn = 0
    recall1 = 0
    recall3 = 0
    baseline_recall3 = 0
    abstained_in_scope = 0
    accepted_out_scope = 0
    details = []
    for row in rows:
        semantic = row["semantic"]
        baseline = row["baseline"]
        expected = row.get("section")
        accepted = bool(semantic) and semantic[0]["score"] >= threshold
        semantic_rank = _section_rank(semantic, expected) if expected else None
        baseline_rank = _section_rank(baseline, expected) if expected else None
        if row["answerable"]:
            recall1 += semantic_rank == 1 and accepted
            recall3 += bool(semantic_rank and semantic_rank <= 3)
            baseline_recall3 += bool(baseline_rank and baseline_rank <= 3)
            if not accepted:
                abstained_in_scope += 1
            predicted = semantic[0] if accepted and semantic else None
            if predicted and expected and _normalized(expected) in _normalized(predicted["title"]):
                concept_tp += 1
            elif predicted:
                concept_fp += 1
            else:
                concept_fn += 1
        elif accepted:
            accepted_out_scope += 1
        details.append({
            "id": row["id"],
            "text": row["text"],
            "answerable": row["answerable"],
            "expected_section": expected,
            "semantic_rank": semantic_rank,
            "baseline_rank": baseline_rank,
            "semantic_top_score": semantic[0]["score"] if semantic else 0.0,
            "semantic_accept": accepted,
            "semantic": semantic,
            "baseline": baseline,
        })

    concept_precision = _safe_ratio(concept_tp, concept_tp + concept_fp)
    concept_recall = _safe_ratio(concept_tp, concept_tp + concept_fn)
    out_tp = len(out_scope) - accepted_out_scope
    out_precision = _safe_ratio(out_tp, out_tp + abstained_in_scope)
    out_recall = _safe_ratio(out_tp, len(out_scope))
    answer_tp = len(in_scope) - abstained_in_scope
    answer_precision = _safe_ratio(answer_tp, answer_tp + accepted_out_scope)
    answer_recall = _safe_ratio(answer_tp, len(in_scope))
    return {
        "threshold": round(threshold, 4),
        "cases": len(rows),
        "in_scope_cases": len(in_scope),
        "out_of_scope_cases": len(out_scope),
        "section_recall_at_1": round(_safe_ratio(recall1, len(in_scope)), 4),
        "section_recall_at_3": round(_safe_ratio(recall3, len(in_scope)), 4),
        "baseline_section_recall_at_3": round(
            _safe_ratio(baseline_recall3, len(in_scope)), 4
        ),
        "concept_precision": round(concept_precision, 4),
        "concept_recall": round(concept_recall, 4),
        "concept_f1": round(_f1(concept_precision, concept_recall), 4),
        "out_of_scope_precision": round(out_precision, 4),
        "out_of_scope_recall": round(out_recall, 4),
        "out_of_scope_f1": round(_f1(out_precision, out_recall), 4),
        "answerability_precision": round(answer_precision, 4),
        "answerability_recall": round(answer_recall, 4),
        "answerability_f1": round(_f1(answer_precision, answer_recall), 4),
        "details": details,
    }


def select_threshold(rows: list[dict]) -> dict:
    best = None
    for step in range(300, 801):
        threshold = step / 1000
        metrics = evaluate_rows(rows, threshold)
        if metrics["concept_recall"] < 0.75:
            continue
        objective = (
            0.45 * metrics["concept_f1"]
            + 0.30 * metrics["section_recall_at_3"]
            + 0.25 * metrics["out_of_scope_f1"]
        )
        candidate = (objective, threshold, metrics)
        if best is None or candidate[0] > best[0]:
            best = candidate
    if best is None:
        metrics = evaluate_rows(rows, 1.0)
        return {"threshold": 1.0, "objective": 0.0, "metrics": metrics}
    return {"threshold": best[1], "objective": round(best[0], 4), "metrics": best[2]}


def _load(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def enable_gates(metrics: dict, review_counts: list[int]) -> dict:
    return {
        "semantic_recall_at_3_improves_baseline": (
            metrics["section_recall_at_3"]
            >= metrics["baseline_section_recall_at_3"] + 0.05
        ),
        "concept_f1_at_least_0_75": metrics["concept_f1"] >= 0.75,
        "out_of_scope_f1_at_least_0_80": metrics["out_of_scope_f1"] >= 0.80,
        "two_independent_reviews": bool(review_counts) and min(review_counts) >= 2,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model", default="BAAI/bge-small-zh-v1.5")
    parser.add_argument("--cache-dir")
    args = parser.parse_args()

    cases = _load(args.cases)
    shadow = SemanticSectionShadow(model_name=args.model, cache_dir=args.cache_dir)
    rows = []
    for case in cases:
        semantic = shadow.predict(case["text"], limit=3)
        baseline = rank_sections(case["text"], limit=3)
        rows.append({
            **case,
            "semantic": [
                {
                    "chapter_id": item.chapter_id,
                    "section_id": item.section_id,
                    "title": item.title,
                    "score": item.score,
                }
                for item in semantic
            ],
            "baseline": [
                {
                    "chapter_id": item.chapter_id,
                    "section_id": item.section_id,
                    "title": item.title,
                    "score": item.score,
                }
                for item in baseline
            ],
        })

    calibration = [row for row in rows if row["split"] == "calibration"]
    evaluation = [row for row in rows if row["split"] == "evaluation"]
    selected = select_threshold(calibration)
    threshold = selected["threshold"]
    calibration_metrics = selected["metrics"]
    evaluation_metrics = evaluate_rows(evaluation, threshold)
    review_counts = [int(row.get("review_count", 0)) for row in evaluation]
    gates = enable_gates(evaluation_metrics, review_counts)
    report = {
        "schema": "query-semantic-shadow-v1",
        "model": args.model,
        "active_path_modified": False,
        "selected_threshold": threshold,
        "selection_objective": selected["objective"],
        "calibration": calibration_metrics,
        "evaluation": evaluation_metrics,
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
        "threshold": threshold,
        "calibration": {
            key: calibration_metrics[key]
            for key in ("concept_f1", "section_recall_at_3", "out_of_scope_f1")
        },
        "evaluation": {
            key: evaluation_metrics[key]
            for key in (
                "baseline_section_recall_at_3",
                "section_recall_at_3",
                "concept_f1",
                "out_of_scope_f1",
                "answerability_f1",
            )
        },
        "gates": gates,
        "can_enable": report["can_enable"],
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
