"""冻结评测不能通过旧来源、缺失难题或重复结果抬高指标。"""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.build_layer4_benchmark import digest
from scripts.evaluate_layer4_benchmark import score, validate


class Layer4BenchmarkTests(unittest.TestCase):
    def fixture(self, root):
        directory = root/'chapters/chapter_01'
        directory.mkdir(parents=True)
        pdf = directory/'chapter_01.generated.pdf'
        pdf.write_bytes(b'isolated snapshot fixture, not a rendered PDF')
        version = digest(pdf)
        (root/'manifest.json').write_text('{}')
        (root/'pdf_manifest.json').write_text(json.dumps([{'document_id': 'doc', 'version': version,
                                                        'chapter_id': 1, 'page_count': 1}]))
        (directory/'document.json').write_text(json.dumps({'blocks': [
            {'block_index': 1, 'section_id': 1, 'kind': 'paragraph', 'text': '独立测试原文'}]}))
        support = {'document_id': 'doc', 'version': version, 'chapter_id': 1, 'section_id': 1,
                   'block_id': 1, 'quote': '独立测试原文',
                   'quote_sha256': hashlib.sha256('独立测试原文'.encode()).hexdigest(),
                   'location_status': 'unlocated', 'rects': []}
        return {'schema': 'layer4-benchmark-v1', 'source_files': {str(p.relative_to(root)).replace('\\', '/'): digest(p)
                for p in root.rglob('*') if p.is_file()}, 'cases': [
                    {'id': 'one', 'category': 'definition', 'group_id': 'group', 'split': 'development',
                     'supports': [support], 'teacher_reviewed': False, 'semantic_reference': None}]}

    def test_snapshot_changes_are_rejected(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            data = self.fixture(root)
            self.assertTrue(validate(data, root)['source_snapshot_valid'])
            (root/'manifest.json').write_text('{"changed":true}')
            with self.assertRaisesRegex(ValueError, 'source_snapshot_changed'):
                validate(data, root)

    def test_missing_pdf_snapshot_is_rejected(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            data = self.fixture(root)
            del data['source_files']['chapters/chapter_01/chapter_01.generated.pdf']
            with self.assertRaisesRegex(ValueError, 'document_or_pdf_not_frozen'):
                validate(data, root)

    def test_same_group_cannot_cross_splits(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            data = self.fixture(root)
            data['cases'].append(dict(data['cases'][0], id='two', split='reserved'))
            with self.assertRaisesRegex(ValueError, 'group_crosses_splits'):
                validate(data, root)

    def test_path_escape_and_fake_teacher_review_are_rejected(self):
        for mutation in ('path', 'review'):
            with self.subTest(mutation=mutation), TemporaryDirectory() as temp:
                root = Path(temp)
                data = self.fixture(root)
                if mutation == 'path':
                    data['source_files']['../outside'] = '0'*64
                else:
                    data['cases'][0]['teacher_reviewed'] = True
                with self.assertRaises(ValueError):
                    validate(data, root)

    def test_wrong_version_does_not_count_as_recall(self):
        support = {'document_id': 'doc', 'version': 'new', 'block_id': 1}
        data = {'cases': [{'id': 'one', 'supports': [support]}]}
        run = {'case_id': 'one', 'sources': [{'document_id': 'doc', 'version': 'old',
                                            'location': {'evidence': {'source_block_id': 1}}}]}
        self.assertEqual(score(data, [run])['anchor_recall'], 0)

    def test_missing_runs_are_kept_in_denominator(self):
        support = {'document_id': 'doc', 'version': 'new', 'block_id': 1}
        data = {'cases': [{'id': name, 'supports': [support]} for name in ('one', 'two')]}
        run = {'case_id': 'one', 'status': 'answered', 'sources': [{'document_id': 'doc', 'version': 'new',
               'location': {'evidence': {'source_block_id': 1}}}]}
        result = score(data, [run])
        self.assertEqual(result['anchor_recall'], .5)
        self.assertEqual(result['missing_runs'], ['two'])
        self.assertFalse(result['semantic_quality_passed'])
        with self.assertRaisesRegex(ValueError, 'unknown_or_duplicate_run'):
            score(data, [run, run])


if __name__ == '__main__':
    unittest.main()
