"""目标名称、原件标题和完整段落范围使用同一来源。"""
import json
import tempfile
from pathlib import Path
import unittest
import zipfile

from knowledge.teaching_targets import extract_targets, word_headings


def block(index, text):
    return {'block_index': index, 'kind': 'paragraph', 'text': text}


class TeachingTargetsTests(unittest.TestCase):
    def test_numbered_sentences_and_introduction_children_are_not_goals(self):
        blocks = [block(0, '一、概念的定义'), block(1, '这是一个拥有真实解释和适用条件的概念定义。'),
                  block(2, '二、教材的组织结构'), block(3, '(一)主要介绍研究方法的教材'),
                  block(4, '这里介绍另一部教材的目录，并不是新的专业知识点。'),
                  block(5, '三、实验控制'), block(6, '在当前实验中需要控制不相关因素，保证结果可解释。'),
                  block(7, '1.将屏幕亮度调到最大，再记录实验结果。')]
        headings = {i: {'text': blocks[i]['text'], 'level': 3 if i == 3 else 2} for i in (0, 2, 3, 5)}
        targets, audit = extract_targets(blocks, headings, '概论')
        self.assertEqual([target['title'] for target in targets], ['概念的定义', '实验控制'])
        self.assertEqual(targets[0]['blocks'][-1]['block_index'], 1)
        self.assertEqual(audit[-1]['classification'], 'numbered_body')
        self.assertEqual(audit[2]['classification'], 'introduction_child')

    def test_heading_sentence_does_not_become_a_goal(self):
        blocks = [block(0, '一、记录实验数据。然后计算平均数。'), block(1, '这是实验的具体操作说明，不能截取一句话冒充知识点。')]
        targets, audit = extract_targets(blocks, {0: {'text': blocks[0]['text'], 'level': 2}}, '实验过程')
        self.assertEqual(targets, [])
        self.assertEqual(audit[0]['classification'], 'descriptive_sentence')

    def test_complete_paragraphs_stop_at_real_sibling_and_separate_asides(self):
        blocks = [block(0, '一、基本概念'), block(1, '长段落' * 900), block(2, '该段落仍然属于同一个知识点，不能按两千字提前结束。'),
                  block(3, '拓展阅读'), block(4, '1.扩展阅读的操作说明。'), block(5, '二、实验控制'),
                  block(6, '这是第二个知识点的解释，必须属于后一个真实标题。')]
        headings = {i: {'text': blocks[i]['text'], 'level': 2} for i in (0, 5)}
        targets, _ = extract_targets(blocks, headings, '基础')
        self.assertEqual([item['block_index'] for item in targets[0]['blocks']], [0, 1, 2])
        self.assertEqual(targets[1]['blocks'][0]['block_index'], 5)

    def test_word_outline_inheritance_and_block_alignment(self):
        with tempfile.TemporaryDirectory() as home:
            path = Path(home) / 'book.docx'
            with zipfile.ZipFile(path, 'w') as package:
                package.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                    '<w:body><w:p><w:pPr><w:pStyle w:val="child"/></w:pPr><w:r><w:t>一、真实</w:t></w:r>'
                    '<w:r><w:t>标题</w:t></w:r></w:p><w:tbl/><w:p><w:r><w:t>1.编号正文。</w:t></w:r></w:p></w:body></w:document>')
                package.writestr('word/styles.xml', '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                    '<w:style w:styleId="base"><w:pPr><w:outlineLvl w:val="2"/></w:pPr></w:style>'
                    '<w:style w:styleId="child"><w:basedOn w:val="base"/></w:style></w:styles>')
            self.assertEqual(word_headings(path, 'fixture'), {0: {'level': 2, 'text': '一、真实标题'}})

    def test_real_book_targets_have_original_headings_and_first_next_is_teachable(self):
        from knowledge.course_navigation import outline, resolve
        units = outline()
        self.assertEqual({unit['chapter_id'] for unit in units}, set(range(1, 12)))
        first = resolve('学习第一章')
        following = resolve('下一知识点', cursor=first)
        self.assertEqual(following['title'], '什么是科学')
        for unit in units:
            self.assertTrue(unit['source_title'])
            self.assertGreater(len(unit['blocks']), 1)
            self.assertEqual(unit['source_block_ids'], [b['block_index'] for b in unit['blocks']])
            self.assertNotIn('主要讲', unit['title'])
            self.assertNotIn('。', unit['title'])
        self.assertEqual(resolve('下一步推导', cursor=first)['id'], first['id'])
        self.assertEqual(resolve('继续这个例子', cursor=first)['id'], first['id'])


if __name__ == '__main__':
    unittest.main()
