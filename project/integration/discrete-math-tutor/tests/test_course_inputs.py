"""全书固定输入只写临时目录；拒绝缺章、越界和冻结后变更。"""
import hashlib
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from PIL import Image
from scripts.freeze_course_inputs import freeze, inventory, safe_path, verify


class CourseInputsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'source'
        self.root.mkdir()
        image = BytesIO()
        Image.new('RGB', (100, 100), 'white').save(image, format='PNG')
        data = image.getvalue()
        digest = lambda value: hashlib.sha256(value).hexdigest()
        chapters, sources, pdfs = [], [], []
        for number in range(1, 12):
            relative = Path('chapters') / f'chapter_{number:02d}'
            chapter = self.root / relative
            chapter.mkdir(parents=True)
            docx = chapter / 'source.docx'
            with zipfile.ZipFile(docx, 'w') as package:
                package.writestr('word/media/image.png', data)
            source_sha = digest(docx.read_bytes())
            (chapter / 'image.png').write_bytes(data)
            (chapter / 'document.json').write_text(json.dumps({'docx_sha256': source_sha, 'blocks': []}))
            (chapter / f'chapter_{number:02d}.generated.pdf').write_bytes(b'pdf-fixture')
            asset = {'id': f'image-{number}', 'filename': 'image.png', 'sha256': digest(data),
                'source_sha256': source_sha, 'package_part': 'word/media/image.png', 'review_status': 'pending'}
            (chapter / 'assets.json').write_text(json.dumps([asset]))
            for name in ('chunks.jsonl', 'text.txt', 'formulas.json', 'pdf_locations.json', 'word_pages.json'):
                (chapter / name).write_text('[]')
            chapters.append({'id': number, 'title': f'第{number}章', 'sections': []})
            sources.append({'chapter_id': number, 'docx': (relative / 'source.docx').as_posix(), 'source_sha256': source_sha})
            pdfs.append({'chapter_id': number, 'document_id': str(number), 'version': digest(b'pdf-fixture')})
        (self.root / 'manifest.json').write_text(json.dumps({'course_id': 'fixture', 'status': 'staging',
            'chapters': chapters, 'full_import': {'chapters': sources}}))
        (self.root / 'pdf_manifest.json').write_text(json.dumps(pdfs))
        (self.root / 'import_report.json').write_text('{}')
        (self.root / 'rag_index.sqlite3').write_bytes(b'existing-index-must-not-change')

    def test_full_book_can_be_frozen_verified_and_transferred_without_original_source(self):
        destination = Path(self.temp.name) / 'snapshot'
        report = freeze(self.root, destination)
        self.assertEqual(len(report['chapters']), 11)
        self.assertEqual(report['asset_counts'], {'candidate_pending_review': 11})
        self.assertFalse(report['ready'])
        self.assertFalse((destination / 'course/rag_index.sqlite3').exists())
        self.assertEqual(verify(destination)['snapshot_id'], report['snapshot_id'])
        with self.assertRaises(FileExistsError):
            freeze(self.root, destination)
        (destination / 'course/chapters/chapter_01/image.png').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, '冻结输入已变化'):
            verify(destination)

    def test_missing_chapter_and_external_asset_are_rejected(self):
        path = self.root / 'manifest.json'
        manifest = json.loads(path.read_bytes())
        manifest['chapters'].pop()
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, '完整 11 章'):
            inventory(self.root)
        with self.assertRaisesRegex(ValueError, '越出课程目录'):
            safe_path(self.root, '../outside-secret')


if __name__ == '__main__':
    unittest.main()
