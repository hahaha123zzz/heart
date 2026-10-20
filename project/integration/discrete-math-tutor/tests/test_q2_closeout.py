"""Q2 接续使用真实教学状态；换版测试只写临时目录。"""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from knowledge import course_navigation as nav


class ContinuationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.first = nav.resolve('学习第一章')

    def test_generic_commands_depend_on_previous_activity(self):
        for text in ('我懂了，下一部分', '下一步', '继续', '接下来'):
            with self.subTest(text=text):
                next_unit = nav.resolve(text, cursor=self.first)
                self.assertNotEqual(next_unit['id'], self.first['id'])
                current = nav.resolve(text, cursor=self.first, activity={'within_point': True})
                self.assertEqual(current['id'], self.first['id'])
                self.assertEqual(current['continuation_action'], 'continue_current')
                waiting = nav.resolve(text, cursor=self.first, activity={'awaiting_answer': True})
                self.assertEqual(waiting['continuation_action'], 'await_answer')
                self.assertNotIn('id', waiting)

    def test_example_and_derivation_keep_target_even_with_generic_words(self):
        for text in ('下一步推导', '继续这个例子', '这个例子接下来怎么算', '继续刚才的证明'):
            with self.subTest(text=text):
                target = nav.resolve(text, cursor=self.first)
                self.assertEqual(target['id'], self.first['id'])
                self.assertEqual(target['mode'], 'repeat')
                self.assertEqual(nav.resolve(text)['status'], 'clarify')

    def test_actual_answer_is_delegated_to_existing_answer_pipeline(self):
        self.assertIsNone(nav.resolve('我选A，接下来', cursor=self.first,
            activity={'awaiting_answer': True}))
        target = nav.resolve('下一个知识点', cursor=self.first, activity={'awaiting_answer': True})
        self.assertNotEqual(target['id'], self.first['id'])
        self.assertFalse(target['covered'])

    def test_negation_does_not_override_same_point_guard(self):
        for message in ('不要继续这个例子', '先不进入下一章'):
            self.assertIsNone(nav.resolve(message, cursor=self.first))

    def test_activity_is_refreshed_from_last_result_without_answer_keys(self):
        memory = SimpleNamespace(repo=SimpleNamespace(memory_epoch=lambda *args: 7))
        row = {'epoch': 7, 'knowledge_point': self.first['title'], 'result': {
            'answer_status': 'answered', 'course_navigation': self.first,
            'question_spec': {'stem': '判断题', 'correct_answer': 'secret'},
            'instructional_move': {'action': 'ask_question'}}}
        cursor = nav.previous_cursor([row], memory, 'student')
        self.assertTrue(cursor['activity']['awaiting_answer'])
        self.assertNotIn('secret', json.dumps(cursor))
        row['result']['instructional_move']['action'] = 'explain'
        self.assertFalse(nav.previous_cursor([row], memory, 'student')['activity']['awaiting_answer'])

    def test_binding_ties_clarify_and_choice_reuses_source_without_reselection(self):
        units = [dict(self.first, blocks=[{'text': '重复的共同原文'}], source='book', page=1),
                 dict(self.first, id='another', title='另一部分', position=1,
                      blocks=[{'text': '重复的共同原文'}], source='book', page=1)]
        record = nav._record(self.first['chapter_id'])
        reference = {'chapter_id': self.first['chapter_id'], 'section_id': self.first['section_id'],
                     'document_id': record['document_id'], 'version': record['version'], 'text': '重复的共同原文'}
        with patch.object(nav, 'outline', return_value=units):
            result = nav.bind_result({'selection_ref': reference})
            self.assertEqual(result['status'], 'clarify')
            self.assertEqual(len(result['candidates']), 2)
            chosen = nav.resolve('另一部分', cursor=result)
            self.assertEqual(chosen['id'], 'another')
            self.assertEqual(chosen['mode'], 'repeat')

    def test_missing_or_old_reference_version_never_binds(self):
        for version in (None, 'old'):
            reference = {'chapter_id': 1, 'section_id': 1, 'version': version, 'text': '实验心理学'}
            original = dict(reference)
            target = nav.bind_result({'selection_ref': reference})
            self.assertEqual(target['status'], 'clarify')
            self.assertEqual(reference, original)
        self.assertEqual(nav.resolve('第一章', cursor=target)['chapter_id'], 1)


class SourceVersionTests(unittest.TestCase):
    def test_directory_asset_mapping_source_and_original_image_invalidate_path(self):
        import hashlib
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            chapter = root / 'chapters/chapter_01'
            chapter.mkdir(parents=True)
            (chapter / 'source.docx').write_bytes(b'source')
            (chapter / 'image.png').write_bytes(b'image')
            digest = lambda value: hashlib.sha256(value).hexdigest()
            manifest = {'chapters': [{'id': 1, 'title': '第一章', 'sections': [{'id': 1, 'title': '第一节'}]}],
                'full_import': {'chapters': [{'chapter_id': 1, 'docx': 'chapters/chapter_01/source.docx',
                    'source_sha256': digest(b'source')}]}}
            (root / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
            (root / 'pdf_manifest.json').write_text(json.dumps([{'chapter_id': 1,
                'document_id': 'book', 'version': 'a' * 64, 'sections': [{'id': 1, 'page': 1}]}]), encoding='utf-8')
            (chapter / 'document.json').write_text(json.dumps({'source': 'book', 'blocks': [
                {'block_index': 1, 'section_id': 1, 'kind': 'paragraph', 'text': '一、实验变量'},
                {'block_index': 2, 'section_id': 1, 'kind': 'paragraph', 'text': '这里保存对应目标的完整真实教材正文，用于验证来源变化。'}]}), encoding='utf-8')
            assets_path = chapter / 'assets.json'
            assets_path.write_text(json.dumps([{'filename': 'image.png', 'sha256': digest(b'image')}]), encoding='utf-8')
            with patch.object(nav, 'PSYCHOLOGY_DIR', root), patch('knowledge.course_release.PSYCHOLOGY_DIR', root), patch.object(
                    nav, 'word_headings', return_value={1: {'level': 2, 'text': '一、实验变量'}}):
                first = nav.outline()[0]
                self.assertTrue(first['source_valid'])
                for path, content in ((root / 'manifest.json', json.dumps(manifest | {'title': '新版'}).encode()),
                                      (chapter / 'image.png', b'new-image'),
                                      (assets_path, b'[]'), (chapter / 'source.docx', b'new-source')):
                    with self.subTest(path=path.name):
                        original = path.read_bytes()
                        path.write_bytes(content)
                        changed = nav.outline()
                        self.assertTrue(not changed or changed[0]['version'] != first['version'])
                        self.assertEqual(nav.resolve('继续', cursor=first)['status'], 'clarify')
                        path.write_bytes(original)


if __name__ == '__main__':
    unittest.main()
