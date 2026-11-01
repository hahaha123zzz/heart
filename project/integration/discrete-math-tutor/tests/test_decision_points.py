"""决策点集：120 条工程回归 + 30 条留出集。"""
import json
import unittest
from pathlib import Path

from agents.input_understanding import labels as labeler
from agents.input_understanding import ontology

FIXTURES = Path(__file__).parent / 'fixtures'


def load(name):
    return [json.loads(line) for line in (FIXTURES / name).read_text(encoding='utf-8').splitlines()
            if line.strip()]


def expected(case):
    return {(dimension, label) for dimension, values in case['labels'].items() for label in values}


def predicted(text):
    return {(row.dimension, row.label) for row in labeler.extract(text)}


class DecisionPointTests(unittest.TestCase):
    def check_schema(self, name, count):
        cases = load(name)
        self.assertEqual(len(cases), count)
        self.assertEqual(len({case['text'] for case in cases}), count)
        for case in cases:
            self.assertIsInstance(case['labels'], dict)
            for dimension, values in case['labels'].items():
                self.assertIn(dimension, ontology.labels())
                for label in values:
                    self.assertTrue(ontology.valid_label(dimension, label))
        return cases

    def test_engineering_set_is_valid(self):
        self.check_schema('decision_points_v1.jsonl', 120)

    def test_holdout_set_is_valid(self):
        self.check_schema('holdout_v1.jsonl', 30)

    def test_engineering_set_micro_f1(self):
        cases = self.check_schema('decision_points_v1.jsonl', 120)
        tp = fp = fn = 0
        for case in cases:
            want, got = expected(case), predicted(case['text'])
            tp += len(want & got)
            fp += len(got - want)
            fn += len(want - got)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        self.assertGreaterEqual(f1, 0.95)


if __name__ == '__main__':
    unittest.main()
