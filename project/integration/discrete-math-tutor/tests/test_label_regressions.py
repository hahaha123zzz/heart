"""B1 回归：混淆的名词/动词歧义，以及不追同义词的策略。"""
import json
import unittest
from pathlib import Path

from agents.input_understanding import labels as labeler

FIXTURE = Path(__file__).parent / 'fixtures' / 'label_regressions_v1.jsonl'


class LabelRegressionTests(unittest.TestCase):
    def test_cases(self):
        cases = [json.loads(line) for line in FIXTURE.read_text(encoding='utf-8').splitlines()
                 if line.strip()]
        self.assertEqual(len(cases), 4)
        for case in cases:
            with self.subTest(text=case['text']):
                got = {(row.dimension, row.label) for row in labeler.extract(case['text'])}
                want = {(dimension, label) for dimension, values in case['labels'].items()
                        for label in values}
                self.assertEqual(got, want)


if __name__ == '__main__':
    unittest.main()
