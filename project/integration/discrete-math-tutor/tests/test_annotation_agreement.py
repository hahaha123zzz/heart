"""κ 工具：完美一致、已知分歧、case_id 不一致。"""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / 'scripts' / 'annotation_agreement.py'
spec = importlib.util.spec_from_file_location('annotation_agreement', SCRIPT)
agreement = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agreement)


def write(tmp, name, rows):
    path = Path(tmp) / name
    path.write_text('\n'.join(json.dumps(row, ensure_ascii=False) for row in rows), encoding='utf-8')
    return path


def case(index, **labels):
    return {'case_id': f'c{index}', 'labels': {key: list(value) for key, value in labels.items()}}


class AgreementTests(unittest.TestCase):
    def test_unfinished_human_template_is_not_scored_as_abstention(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp,'pending.jsonl',[{'case_id':'pending','labels':{},'reviewed':False}])
            with self.assertRaisesRegex(ValueError,'unreviewed'):
                agreement.load(path)

    def test_constant_agreement_has_no_defined_kappa(self):
        agree, score = agreement.kappa([(True, True), (True, True)])
        self.assertEqual(agree, 1.0)
        self.assertIsNone(score)
        report = agreement.compare({'c1': {'engagement': {'skip'}}},
                                   {'c1': {'engagement': {'skip'}}})
        self.assertIsNone(report['engagement']['macro_kappa'])

    def test_second_annotator_only_dimension_is_not_lost(self):
        report = agreement.compare({'c1': {}}, {'c1': {'engagement': {'skip'}}})
        self.assertEqual(report['engagement']['exact_agreement'], 0.0)
        self.assertIn('skip', report['engagement']['labels'])

    def test_missing_and_empty_annotation_agree(self):
        report = agreement.compare({'c1': {}, 'c2': {'engagement': {'skip'}}},
                                   {'c1': {'engagement': set()}, 'c2': {'engagement': {'skip'}}})
        self.assertEqual(report['engagement']['exact_agreement'], 1.0)

    def test_duplicate_case_ids_cannot_silently_replace_annotations(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, 'duplicate.jsonl', [case(1), case(1, engagement=['skip'])])
            with self.assertRaisesRegex(ValueError, 'duplicate case_id'):
                agreement.load(path)

    def test_perfect_agreement(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = write(tmp, 'a.jsonl', [case(1, difficulty_locus=['memory']), case(2, difficulty_locus=[])])
            b = write(tmp, 'b.jsonl', [case(1, difficulty_locus=['memory']), case(2, difficulty_locus=[])])
            report = agreement.compare(agreement.load(a), agreement.load(b))
        self.assertEqual(report['difficulty_locus']['exact_agreement'], 1.0)
        self.assertEqual(report['difficulty_locus']['labels']['memory']['kappa'], 1.0)

    def test_known_kappa_value(self):
        rows_a = [case(index, difficulty_locus=['memory'] if index <= 5 else []) for index in range(1, 11)]
        rows_b = [case(index, difficulty_locus=['memory'] if index in (1, 2, 3, 4, 6) else [])
                  for index in range(1, 11)]
        with tempfile.TemporaryDirectory() as tmp:
            report = agreement.compare(agreement.load(write(tmp, 'a.jsonl', rows_a)),
                                       agreement.load(write(tmp, 'b.jsonl', rows_b)))
        row = report['difficulty_locus']['labels']['memory']
        self.assertAlmostEqual(row['agreement'], 0.8)
        self.assertAlmostEqual(row['kappa'], 0.6)

    def test_mismatched_cases_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                agreement.compare(agreement.load(write(tmp, 'a.jsonl', [case(1)])),
                                  agreement.load(write(tmp, 'b.jsonl', [case(2)])))


if __name__ == '__main__':
    unittest.main()
