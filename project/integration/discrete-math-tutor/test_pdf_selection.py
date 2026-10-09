"""验证 PDF 定位、选区信任边界、学生记忆隔离与引用保存。"""
import unittest,json,uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import fitz
from fastapi.testclient import TestClient
from knowledge.pdf_reader import (documents,document,pdf_path,PDFSelection,validate_selection,resolve_selection,crop_path)
from memory.memory_manager import MemoryManager
from memory.selection_memory import selection_memory
from agents.pdf_selection_tutor import explain_selection
from agents.quality_checker import QualityResult
from llm.client import LLMClient,LLMError

class PDFSelectionTests(unittest.TestCase):
    def area(self,chapter=3,page=8):
        record=document(f'chapter-{chapter:02d}')
        return PDFSelection(document_id=record['document_id'],version=record['version'],kind='area',
          rects=[{'page':page,'x1':.15,'y1':.09,'x2':.88,'y2':.18}],text='伪造的网页文字：答案为999')
    def test_all_documents_and_headings_verified(self):
        self.assertEqual(len(documents()),10)
        self.assertEqual(sum(d['page_count'] for d in documents()),223)
        for record in documents():
            with fitz.open(pdf_path(record)) as pdf:
                for section in record['sections']:
                    self.assertTrue(section['verified'])
                    if section['id']!=1:
                        self.assertIn(''.join(section['title'].split()),''.join(pdf[section['page']-1].get_text().split()))
    def test_forged_text_ignored_and_crop_checked(self):
        result=resolve_selection(self.area())
        self.assertNotIn('999',result['text'])
        self.assertIn('二项式',result['context'])
        self.assertEqual(result['section']['id'],6)
        path=result['images'][0]
        self.assertEqual(crop_path(path.stem),path)
        messages=LLMClient._with_images([{'role':'user','content':'教材'}],[path])
        self.assertEqual(messages[-1]['content'][1]['type'],'image_url')
    def test_stale_bounds_and_crosspage_rejected(self):
        selection=self.area();selection.version='0'*64
        with self.assertRaisesRegex(ValueError,'更新'):validate_selection(selection)
        selection=self.area();selection.rects[0].x2=.1
        with self.assertRaisesRegex(ValueError,'坐标'):validate_selection(selection)
        selection=self.area();selection.rects[0].page=999
        with self.assertRaisesRegex(ValueError,'页码'):validate_selection(selection)
        selection=self.area();selection.rects*=3
        with self.assertRaisesRegex(ValueError,'一页'):validate_selection(selection)
    def test_untrusted_image_not_accepted(self):
        with self.assertRaises(LLMError):LLMClient._with_images([{'role':'user','content':'图'}],[Path(__file__)])
    def test_text_reconstruction(self):
        record=document('chapter-07')
        with fitz.open(pdf_path(record)) as pdf:
            found=None
            for n,p in enumerate(pdf):
                for b in p.get_text('blocks'):
                    if '定理7.4' in b[4]:found=(n+1,p,b);break
                if found:break
            n,p,b=found
            selection=PDFSelection(document_id=record['document_id'],version=record['version'],kind='text',rects=[
              {'page':n,'x1':b[0]/p.rect.width,'y1':b[1]/p.rect.height,'x2':b[2]/p.rect.width,'y2':b[3]/p.rect.height}])
            result=resolve_selection(selection)
            self.assertIn('定理7.4',result['text'])
            self.assertIn('路径',result['context'])
    def test_memory_isolation_no_state_advance_and_reload_reference(self):
        memory=MemoryManager();a='pdf-test-'+uuid.uuid4().hex;b='pdf-test-'+uuid.uuid4().hex
        try:
            for student in [a,b]:memory.ensure_student(student)
            memory.add_hypothesis(a,'组合的计数','concept','组合数与排列数混淆',.8)
            mem_a=selection_memory(memory,a,'3.2.2 组合的计数','组合数','解释公式')
            mem_b=selection_memory(memory,b,'3.2.2 组合的计数','组合数','解释公式')
            self.assertTrue(mem_a['learning_states'])
            self.assertFalse(mem_b['learning_states'])
            calls=[]
            def generate(messages,**kwargs):
                calls.append((messages,kwargs));return '这个公式是牛顿二项式展开式，组合数表示从 n 个因子中选择对应项的方式数。[1]'
            checker=SimpleNamespace(check=lambda *args,**kwargs:QualityResult(passed=True))
            tutor=SimpleNamespace(memory=memory,llm=SimpleNamespace(chat=generate),quality_checker=checker)
            before=memory.get_state(a,'3.2.2 组合的计数').model_dump()
            result=explain_selection(tutor,a,'解释这个公式',self.area(),'production')
            self.assertEqual(before,memory.get_state(a,'3.2.2 组合的计数').model_dump())
            self.assertTrue(calls[0][1]['image_paths'])
            self.assertIn('组合数与排列数混淆',calls[0][0][-1]['content'])
            restored=memory.repo.get_conversation_with_figures(a)
            self.assertEqual(restored[-1]['selection_ref'],result['selection_ref'])
            self.assertIsNone(memory.get_lesson_plan(a,'3.2.2 组合的计数'))
        finally:
            memory.reset(a);memory.reset(b)
    def test_invalid_selection_rejected_before_model_for_both_routes(self):
        import main
        selection=self.area();selection.version='0'*64
        with patch.object(main.orchestrator.llm,'chat') as generate,TestClient(main.app) as client:
            for endpoint in ['/api/chat','/api/chat/stream']:
                response=client.post(endpoint,json={'student_id':'pdf-invalid','message':'解释','selection':selection.model_dump()})
                self.assertEqual(response.status_code,422)
            generate.assert_not_called()
if __name__=='__main__':unittest.main()
