"""使用真实原生阅读库验证跨用户隔离、内容换版和重复导入。"""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from integrations.deeptutor import course_reading


class NativeReadingScopeTests(unittest.TestCase):
    def setUp(self):
        from deeptutor.reading import ReadingCatalogStore, ReadingStore
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.pdf=self.root/'chapter.pdf';self.write_pdf('first version')
        self.owner='A'
        import sqlite3
        self.connections=[];connect=sqlite3.connect
        def tracked(*args,**kwargs):
            connection=connect(*args,**kwargs);self.connections.append(connection);return connection
        self.connect_patch=patch('sqlite3.connect',side_effect=tracked);self.connect_patch.start()
        self.original_catalog=ReadingCatalogStore
        self.catalog=patch('deeptutor.reading.ReadingCatalogStore',side_effect=lambda:ReadingCatalogStore(self.root/self.owner))
        self.store=patch('deeptutor.reading.ReadingStore',side_effect=lambda:ReadingStore(self.root/self.owner))
        self.original_documents=course_reading._course_documents
        self.rows=patch.object(course_reading,'_course_documents',side_effect=lambda:('course','课程',[{
            'document_id':'doc','chapter_id':1,'title':'第一章','path':self.pdf,
            'version':hashlib.sha256(self.pdf.read_bytes()).hexdigest()}]))
        self.cache=patch.object(course_reading,'_CACHE',{},create=True)
        for guard in (self.catalog,self.store,self.rows,self.cache):guard.start()
    def tearDown(self):
        for guard in (self.cache,self.rows,self.store,self.catalog):guard.stop()
        for connection in self.connections:connection.close()
        self.connect_patch.stop();self.temp.cleanup()
    def write_pdf(self,text):
        import pymupdf
        with pymupdf.open() as pdf:
            page=pdf.new_page();page.insert_text((72,72),text)
            self.pdf.write_bytes(pdf.tobytes())
    def test_each_owner_gets_their_own_reading_workspace(self):
        first=course_reading.ensure_course_reading();self.owner='B'
        second=course_reading.ensure_course_reading()
        self.assertNotEqual(first['workspace_id'],second['workspace_id'])
        self.assertEqual(len(self.original_catalog(self.root/'B').list_workspaces()),1)
    def test_changed_bytes_under_same_filename_create_new_material(self):
        first=course_reading.ensure_course_reading()
        self.write_pdf('changed version')
        second=course_reading.ensure_course_reading()
        self.assertNotEqual(first['materials'][0]['material_id'],second['materials'][0]['material_id'])
        self.assertEqual(first['workspace_id'],second['workspace_id'])
    def test_repeat_import_preserves_one_material_and_workspace(self):
        first=course_reading.ensure_course_reading();second=course_reading.ensure_course_reading()
        self.assertEqual(first['materials'],second['materials'])
        catalog=self.original_catalog(self.root/'A')
        self.assertEqual(len(catalog.list_workspaces()),1)
        self.assertEqual(len(catalog.list_materials()),1)


    def test_repeat_import_keeps_existing_material_title(self):
        prepared=course_reading.ensure_course_reading()
        catalog=self.original_catalog(self.root/'A')
        item=catalog.get_material(prepared['materials'][0]['material_id'])
        catalog.upsert_material(content_id=item.content_id,material_id=item.material_id,filename=item.filename,
            title='我的阅读标题',source_kind=item.source_kind,mime=item.mime,render_mode=item.render_mode,status='ready')
        course_reading.ensure_course_reading()
        self.assertEqual(catalog.get_material(item.material_id).title,'我的阅读标题')

    def test_declared_pdf_version_must_match_actual_bytes(self):
        import knowledge.pdf_reader
        with patch('knowledge.course_config.PSYCHOLOGY_DIR',self.root),              patch('knowledge.pdf_reader.documents',return_value=[{'document_id':'doc','chapter_id':1,'version':'0'*64}]),              patch('knowledge.pdf_reader.pdf_path',return_value=self.pdf):
            with self.assertRaisesRegex(ValueError,'版本不一致'):
                self.original_documents()
