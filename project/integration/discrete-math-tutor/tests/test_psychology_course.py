"""在独立进程验证原教材接口接入全书，不导入main或学生数据库。"""
import hashlib,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class PsychologyCourseIntegrationTests(unittest.TestCase):
    def test_original_course_and_pdf_interfaces_use_full_book(self):
        script='''
from fastapi import FastAPI
from fastapi.testclient import TestClient
from knowledge.course import chapters,QUIZZES
from knowledge.textbook import load_textbook
from knowledge.pdf_reader import documents,document,document_for_chapter,pdf_path,PDFSelection,resolve_selection
from knowledge.course_config import PSYCHOLOGY_DIR
from knowledge.structured_index import build_records
from scripts.build_rag_index import INDEX
from agents.task_context_builder import TaskContextBuilder
from models.task_context import ReaderLocation
from web_api import router
from practice_api import catalog,keys,question
import fitz,hashlib,json
assert len(chapters())==11
assert sum(len(c['sections']) for c in chapters())==37
assert QUIZZES=={}
assert catalog()['questions']==[] and keys()=={}
try:
 question('math-old-question')
 raise AssertionError('旧练习没有被隔离')
except Exception as error:assert getattr(error,'status_code',None)==404
chunks=load_textbook()
assert {c.chapter_id for c in chunks}==set(range(1,12))
assert all(c.chunk_id.startswith('experimental-psychology-3:') for c in chunks)
assert INDEX==PSYCHOLOGY_DIR/'rag_index.sqlite3'
assert {r['chapter_id'] for r in build_records()}==set(range(1,12))
records=documents()
assert sum(r['page_count'] for r in records)==376
for record in records:
 assert hashlib.sha256(pdf_path(record).read_bytes()).hexdigest()==record['version']
 assert all(s['verified'] for s in record['sections'])
assert document('chapter-11') is None
assert document('chapter-04') is None
app=FastAPI();app.include_router(router);client=TestClient(app)
assert client.get('/api/course/reading-map').json()=={}
assert len(client.get('/api/course/chapters').json())==11
for chapter in chapters():
 for section in chapter['sections']:
  response=client.get(f'/api/course/chapters/{chapter["id"]}/sections/{section["id"]}')
  assert response.status_code==200
  data=response.json()
  assert data['pdf']['document_id']==f'experimental-psychology-3:chapter-{chapter["id"]:02d}'
  assert data['figures']==[] and data['blocks']==[]
assert client.get('/api/course/chapters/12/sections/1').status_code==404
record=document_for_chapter(11);section=record['sections'][2]
selected=resolve_selection(PDFSelection(document_id=record['document_id'],version=record['version'],kind='text',rects=[section['rect']],text='伪造教材'))
assert '伪造教材' not in selected['text']
assert ''.join(section['title'].split()) in ''.join(selected['text'].split())
assert selected['record']['chapter_id']==11
built=TaskContextBuilder().build(student_id='isolated-check',message='解释本节',reader_location=ReaderLocation(chapter_id=11,section_id=3))
assert built.objects[0].version==record['version']
try:
 resolve_selection(PDFSelection(document_id='chapter-04',version=record['version'],kind='text',rects=[section['rect']]))
 raise AssertionError('旧书引用未被拒绝')
except ValueError:pass
print('PASS: 原教材接口11章37节、376页版本、全书索引、选区与旧引用隔离')
'''
        with tempfile.TemporaryDirectory() as temporary:
            env=os.environ|{'TUTOR_COURSE':'experimental-psychology-3','DATABASE_URL':'sqlite:///'+str(Path(temporary)/'isolated.db')}
            result=subprocess.run([sys.executable,'-X','utf8','-c',script],cwd=ROOT,env=env,text=True,capture_output=True,encoding='utf-8',timeout=60)
            self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
            self.assertFalse((Path(temporary)/'isolated.db').exists(),'教材只读接口不应创建学生数据库')

if __name__=='__main__':unittest.main()
