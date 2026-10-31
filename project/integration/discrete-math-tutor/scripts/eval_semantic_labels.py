"""离线评估语义标签（规则路径，不调模型）。

用法：
    python scripts/eval_semantic_labels.py [jsonl ...]

默认评估 120 条工程回归集，另打印 30 条留出集的召回，用于观察规则泛化。
指标只看标签层；教学效果不在本脚本范围内。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DEFAULT = [ROOT / "tests/fixtures/decision_points_v1.jsonl",
           ROOT / "tests/fixtures/holdout_v1.jsonl"]


def load(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()]


def predicted(text):
    from agents.input_understanding import labels as labeler
    return {(row.dimension, row.label) for row in labeler.extract(text)}


def expected(case):
    return {(dimension, label) for dimension, values in case.get("labels", {}).items()
            for label in values}


def score(cases):
    from agents.input_understanding import ontology
    dims = list(ontology.labels())
    stats = {name: {"tp": 0, "fp": 0, "fn": 0, "support": 0, "empty": 0} for name in dims}
    for case in cases:
        want, got = expected(case), predicted(case["text"])
        for name in dims:
            want_d = {row for row in want if row[0] == name}
            got_d = {row for row in got if row[0] == name}
            stats[name]["tp"] += len(want_d & got_d)
            stats[name]["fp"] += len(got_d - want_d)
            stats[name]["fn"] += len(want_d - got_d)
            stats[name]["support"] += len(want_d)
            if not want_d and not got_d:
                stats[name]["empty"] += 1
    return stats


def prf(row):
    precision = row["tp"] / (row["tp"] + row["fp"]) if row["tp"] + row["fp"] else 0.0
    recall = row["tp"] / (row["tp"] + row["fn"]) if row["tp"] + row["fn"] else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def report(title, cases):
    stats = score(cases)
    print(f"== {title}（{len(cases)} 条）")
    print(f"{'dimension':22}{'P':>7}{'R':>7}{'F1':>7}{'support':>9}{'abstain':>9}")
    totals = {"tp": 0, "fp": 0, "fn": 0, "support": 0, "empty": 0}
    for name, row in stats.items():
        precision, recall, f1 = prf(row)
        totals = {key: totals[key] + row[key] for key in totals}
        print(f"{name:22}{precision:7.2f}{recall:7.2f}{f1:7.2f}{row['support']:9}{row['empty']:9}")
    precision, recall, f1 = prf(totals)
    print(f"{'micro':22}{precision:7.2f}{recall:7.2f}{f1:7.2f}{totals['support']:9}{totals['empty']:9}")
    for name, row in stats.items():
        precision, recall, f1 = prf(row)
        print(f"macro[{name}] P={precision:.2f} R={recall:.2f} F1={f1:.2f}")
    print()


def main(paths):
    for path in paths or DEFAULT:
        path = Path(path)
        if not path.exists():
            print(f"missing: {path}")
            continue
        report(path.stem, load(path))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
