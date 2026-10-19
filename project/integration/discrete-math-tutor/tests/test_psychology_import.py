import unittest
import tempfile,json,sqlite3,io
from zipfile import ZipFile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch,Mock
from xml.etree import ElementTree as ET
from scripts.import_psychology_sample import chapter_groups,NUMBERS,NS,SECTION,write_chapter
from scripts.parse_converted_textbook import heading_section,FIGURE_RE

class PsychologyImportTests(unittest.TestCase):
    def paragraph(self,text):
        p=ET.Element('{'+NS['w']+'}p');run=ET.SubElement(p,'{'+NS['w']+'}r');ET.SubElement(run,'{'+NS['w']+'}t').text=text;return p
    def test_batch_chapters_do_not_mutate_source_zip_offsets(self):
        original=io.BytesIO()
        xml=('<w:document xmlns:w="'+NS['w']+'"><w:body><w:p/></w:body></w:document>').encode()
        with ZipFile(original,'w') as package:
            package.writestr('word/document.xml',xml);package.writestr('word/styles.xml',b'<styles/>')
        original.seek(0)
        with ZipFile(original) as package,tempfile.TemporaryDirectory() as directory:
            for chapter in range(3):
                target=Path(directory)/f'{chapter}.docx'
                write_chapter(package,xml,[self.paragraph('第'+str(chapter)+'章')],None,target)
                with ZipFile(target) as output:self.assertEqual(output.read('word/styles.xml'),b'<styles/>')
                self.assertEqual(package.read('word/document.xml'),xml)
    def test_only_actual_standalone_chapters_are_navigation(self):
        body=ET.Element('{'+NS['w']+'}body')
        for number in NUMBERS:
            body.extend([self.paragraph('第'+number+'章'),self.paragraph('本书章节标题'),self.paragraph('第一节 概述')])
            body.append(self.paragraph('第一章 引用其他教材目录'))
        groups=chapter_groups(body)
        self.assertEqual(len(groups),11)
        self.assertTrue(all(len(group['sections'])==1 for group in groups))
        body.remove(body[-4])
        with self.assertRaises(ValueError):chapter_groups(body)
    def test_new_section_style_and_figure_number_preserve_old_defaults(self):
        self.assertEqual(heading_section('第二节 单自变量被试间设计','旧标题',SECTION),'第二节 单自变量被试间设计')
        self.assertEqual(heading_section('4.1.2 逻辑联结词','旧标题'),'4.1.2 逻辑联结词')
        self.assertEqual(FIGURE_RE.findall('图4-2与图7.11'),['图4-2','图7.11'])
        from knowledge.hybrid_retrieval import _reference_present
        self.assertTrue(_reference_present('表4-6 实验设计',{'表4-6'}))
        self.assertFalse(_reference_present('表4-4 其他实验',{'表4-6'}))
    def test_separate_index_rebuild_preserves_old_index_and_skips_math_rules(self):
        from scripts.build_rag_index import build_index
        from knowledge.hybrid_retrieval import retrieve_hybrid,INDEX
        before=INDEX.stat().st_mtime_ns
        record={'id':'psych:ch04:b1','parent_id':'psych:ch04:b1','chapter_id':4,'source':'实验心理学',
            'section':'被试间设计','section_id':1,'page':1,'block_start':1,'block_end':1,'kind':'text',
            'text':'被试间设计指每名被试只接受一种实验处理条件。','asset_ids':[]}
        model=Mock();model.embed.side_effect=lambda contents,**kwargs:iter([[1.,0.,0.] for _ in contents])
        with tempfile.TemporaryDirectory() as folder,patch('fastembed.TextEmbedding',return_value=model),patch('knowledge.semantic_chunks.refine',side_effect=lambda rows,*args:rows):
            target=Path(folder)/'sample.sqlite3'
            for _ in range(2):build_index(target,records=[record],embed=True,index_logic_formulas=False)
            with closing(sqlite3.connect(target)) as db:
                self.assertEqual(db.execute('select count(*) from chunks').fetchone()[0],1)
                self.assertIsNone(db.execute("select name from sqlite_master where name='logic_formulas'").fetchone())
            with patch.dict('os.environ',{'RAG_RERANK_MODEL':''}),patch('knowledge.hybrid_retrieval._embedder',return_value=model):
                found=retrieve_hybrid('被试间设计',[],index_path=target)
            self.assertTrue(found);self.assertEqual(found[0].source,'实验心理学')
        self.assertEqual(INDEX.stat().st_mtime_ns,before)

if __name__=='__main__':unittest.main()
