"""本轮验收暴露的多概念覆盖与OMML结构回归，不调用外部模型。"""
import os,subprocess,sys,tempfile,unittest
from pathlib import Path
from xml.etree import ElementTree as ET
from scripts.parse_converted_textbook import NS,paragraph_text

ROOT=Path(__file__).resolve().parents[1]

class FormulaTextTests(unittest.TestCase):
    def parse(self,body):
        return paragraph_text(ET.fromstring('<w:p xmlns:w="'+NS['w']+'" xmlns:m="'+NS['m']+'">'+body+'</w:p>'))

    def test_fraction_keeps_denominator_and_nested_fraction(self):
        fraction='<m:f><m:num><m:r><m:t>44</m:t></m:r></m:num><m:den><m:r><m:t>12</m:t></m:r></m:den></m:f>'
        self.assertEqual(self.parse('<w:r><w:t>DL=</w:t></w:r><m:oMath>'+fraction+'</m:oMath>'),r'DL=\frac{44}{12}')
        self.assertEqual(self.parse('<m:oMath><m:f><m:num>'+fraction+'</m:num><m:den><m:r><m:t>N</m:t></m:r></m:den></m:f></m:oMath>'),r'\frac{\frac{44}{12}}{N}')

    def test_no_bar_stack_is_not_division(self):
        self.assertEqual(self.parse('<m:f><m:fPr><m:type m:val="noBar"/></m:fPr><m:num><m:r><m:t>a</m:t></m:r></m:num><m:den><m:r><m:t>b</m:t></m:r></m:den></m:f>'),r'\substack{a\\b}')

    def test_scripts_root_bar_and_matrix_preserve_structure(self):
        self.assertEqual(self.parse('<m:sSup><m:e><m:r><m:t>X</m:t></m:r></m:e><m:sup><m:r><m:t>2</m:t></m:r></m:sup></m:sSup>'),r'{X}^{2}')
        self.assertEqual(self.parse('<m:sSub><m:e><m:r><m:t>S</m:t></m:r></m:e><m:sub><m:r><m:t>t</m:t></m:r></m:sub></m:sSub>'),r'{S}_{t}')
        self.assertEqual(self.parse('<m:rad><m:e><m:r><m:t>x</m:t></m:r></m:e></m:rad>'),r'\sqrt{x}')
        self.assertEqual(self.parse('<m:bar><m:e><m:r><m:t>X</m:t></m:r></m:e></m:bar>'),r'\overline{X}')
        self.assertEqual(self.parse('<m:d><m:dPr><m:begChr m:val="["/><m:endChr m:val="]"/></m:dPr><m:e><m:m><m:mr><m:e><m:r><m:t>a</m:t></m:r></m:e><m:e><m:r><m:t>b</m:t></m:r></m:e></m:mr></m:m></m:e></m:d>'),r'[\begin{matrix}a & b\end{matrix}]')

    def test_plain_text_tabs_and_breaks_unchanged(self):
        self.assertEqual(self.parse('<w:r><w:t>正文</w:t><w:tab/><w:t>内容</w:t><w:br/><w:t>下一行</w:t></w:r>'),'正文\t内容\n下一行')

class ConceptCoverageTests(unittest.TestCase):
    def test_parent_heading_includes_children_until_peer_heading(self):
        from knowledge.psychology_retrieval import _group
        blocks=[{'section_id':1,'text':text} for text in ['三、设计的应用','(一)选择被试','选择原则正文','1.随机分配','分配方法正文','四、下一主题','另一主题正文']]
        self.assertEqual(_group(blocks,0),blocks[:5])
        self.assertEqual(_group(blocks,1),blocks[1:5])
    def test_multiple_concepts_and_single_concept_modes(self):
        script='''
from unittest.mock import patch
from knowledge.psychology_retrieval import retrieve
with patch('knowledge.psychology_retrieval.retrieve_hybrid',return_value=[]):
 sources=retrieve('自变量、因变量和额外变量的区别',[])
 for concept in ['自变量','因变量','额外变量']:
  assert any('一、'+concept+'的含义' in s.text for s in sources),concept
 assert len(retrieve('自变量、因变量和额外变量的区别',[],limit=2))<=2
 sources=retrieve('什么是单因素随机区组设计',[])
 assert any('每个区组的被试同质' in s.text for s in sources)
 assert any('每名被试随机接受一种处理水平' in s.text for s in sources)
'''
        with tempfile.TemporaryDirectory() as folder:
            env=os.environ|{'TUTOR_COURSE':'experimental-psychology-3','DATABASE_URL':'sqlite:///'+str(Path(folder)/'test.db')}
            result=subprocess.run([sys.executable,'-X','utf8','-c',script],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)

    def test_imported_formula_text_retains_fraction(self):
        import json
        from zipfile import ZipFile
        folder=ROOT/'knowledge/courses/experimental-psychology-3/chapters/chapter_07'
        with ZipFile(next(folder.glob('*.docx'))) as package:
            body=ET.fromstring(package.read('word/document.xml')).find('w:body',NS)
            actual=paragraph_text(list(body)[123])
        self.assertEqual(actual,r'DL=\frac{∑|X-St|}{N}')
        document=json.loads((folder/'document.json').read_text(encoding='utf-8'))
        block=next(b for b in document['blocks'] if b['block_index']==123)
        self.assertEqual(block['text'],actual)

if __name__=='__main__':unittest.main()
