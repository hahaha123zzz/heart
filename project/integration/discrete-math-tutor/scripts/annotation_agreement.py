"""双人标注一致性（Cohen's κ）。

用法：
    python scripts/annotation_agreement.py A.jsonl B.jsonl

两个文件都是 {"case_id": ..., "labels": {维度: [取值...]}}，按 case_id 对齐。
输出每个维度/取值的二分类 κ（存在=1）、维度级完全一致率和宏平均 κ。
κ 低于 0.6 的维度应退回改定义，而不是继续训练模型。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load(path):
    cases = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case = json.loads(line)
        if 'reviewed' in case and case['reviewed'] is not True:
            raise ValueError(f"unreviewed case: {case['case_id']}")
        if case["case_id"] in cases:
            raise ValueError(f"duplicate case_id: {case['case_id']}")
        cases[case["case_id"]] = {dimension: set(values)
                                  for dimension, values in case.get("labels", {}).items()}
    return cases


def kappa(rows):
    """二分类 κ；rows 为 (a_present, b_present)。"""
    n = len(rows)
    if not n:
        return 0.0, None
    agree = sum(1 for a, b in rows if a == b) / n
    a_yes = sum(1 for a, _ in rows if a) / n
    b_yes = sum(1 for _, b in rows if b) / n
    chance = a_yes * b_yes + (1 - a_yes) * (1 - b_yes)
    if chance == 1:
        return agree, None
    return agree, (agree - chance) / (1 - chance)


def compare(a, b):
    shared = sorted(set(a) & set(b))
    if not shared:
        raise ValueError("no shared case_id")
    if set(a) != set(b):
        raise ValueError(f"case_id mismatch: only_a={sorted(set(a) - set(b))[:3]} "
                         f"only_b={sorted(set(b) - set(a))[:3]}")
    dimensions = sorted({dimension for cases in (a, b)
                         for case in cases.values() for dimension in case})
    report = {}
    for dimension in dimensions:
        labels = sorted({label for case in a.values() for label in case.get(dimension, ())}
                        | {label for case in b.values() for label in case.get(dimension, ())})
        rows = [(label in a[case].get(dimension, set()), label in b[case].get(dimension, set()))
                for case in shared for label in labels]
        kappas = {}
        for label in labels:
            pair = [(label in a[case].get(dimension, set()),
                     label in b[case].get(dimension, set())) for case in shared]
            agree, value = kappa(pair)
            kappas[label] = {"kappa": round(value, 3) if value is not None else None, "agreement": round(agree, 3),
                             "support": sum(1 for x, _ in pair if x)}
        exact = sum(1 for case in shared if a[case].get(dimension, set())
                    == b[case].get(dimension, set())) / len(shared)
        defined = [row["kappa"] for row in kappas.values() if row["kappa"] is not None]
        report[dimension] = {"labels": kappas,
                             "exact_agreement": round(exact, 3),
                             "macro_kappa": round(sum(defined) / len(defined), 3) if defined else None}
    return report


def main(paths):
    if len(paths) != 2:
        print(__doc__)
        return 2
    report = compare(load(paths[0]), load(paths[1]))
    print(f"{'dimension':22}{'label':26}{'kappa':>7}{'agree':>7}{'support':>8}")
    for dimension, row in report.items():
        for label, value in row["labels"].items():
            score = f"{value['kappa']:.2f}" if value['kappa'] is not None else 'N/A'
            print(f"{dimension:22}{label:26}{score:>7}{value['agreement']:7.2f}"
                  f"{value['support']:8}")
        print(f"{dimension:22}{'[exact]':26}{row['exact_agreement']:7.2f}"
              f"{'':7}{'':8}  macro_kappa={row['macro_kappa']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
