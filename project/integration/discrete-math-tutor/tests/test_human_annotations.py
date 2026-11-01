import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('human_import',
    Path(__file__).resolve().parents[1]/'scripts/import_semantic_annotations.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class HumanAnnotationTests(unittest.TestCase):
    def row(self,**changes):
        return {'case_id':'human-1','reviewed':'1','annotator_id':'reviewer-B',**changes}

    def test_reviewed_abstention_remains_explicit(self):
        result = module.convert([self.row()])[0]
        self.assertTrue(result['reviewed'])
        self.assertEqual(result['labels']['difficulty_locus'],[])

    def test_unreviewed_template_and_missing_reviewer_are_rejected(self):
        for row in (self.row(reviewed='0'),self.row(annotator_id='')):
            with self.assertRaises(ValueError):module.convert([row])

    def test_invalid_or_duplicate_labels_and_cases_are_rejected(self):
        for rows in ([self.row(engagement='guess')],[self.row(engagement='skip|skip')],
                     [self.row(),self.row()]):
            with self.assertRaises(ValueError):module.convert(rows)

    def test_cognitive_order_is_preserved(self):
        row = module.convert([self.row(cognitive_demand='analyze|evaluate')])[0]
        self.assertEqual(row['labels']['cognitive_demand'],['analyze','evaluate'])
