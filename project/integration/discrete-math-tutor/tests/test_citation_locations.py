import unittest
from dataclasses import replace
from knowledge.textbook import TextbookChunk
from knowledge.proof_units import units_for
from knowledge.figures import get_figure, retrieve_figures
from knowledge.citation_locations import complete_pdf_references

class CitationLocationTests(unittest.TestCase):
    def source(self,label='定义9.7'):
        unit=units_for(9)[label]
        return TextbookChunk('第9章关系（新）.txt',unit.section['title'],label+' 原始召回',frozenset(),chapter_id=9,section_id=unit.section['id'])
    def test_ordinary_definition_gets_verified_pdf_reference(self):
        refs=complete_pdf_references([self.source()],'根据定义判断[1]',[])
        self.assertEqual(refs[0]['source_index'],0)
        self.assertEqual(refs[0]['label'],'定义9.7')
        self.assertEqual(refs[0]['selection_ref']['rects'][0]['page'],17)
    def test_wrong_file_or_section_cannot_create_reference(self):
        for source in [replace(self.source(),source='其他教材.txt'),replace(self.source(),section_id=99)]:
            self.assertEqual(complete_pdf_references([source],'解释[1]',[]),[])
    def test_uncited_source_and_existing_reference_are_not_duplicated(self):
        existing=[{'source_index':0,'label':'原引用','selection_ref':{'rects':[]}}]
        self.assertEqual(complete_pdf_references([self.source()],'解释[1]',existing),existing)
        self.assertEqual(complete_pdf_references([self.source()],'无引用',[]),[])
    def test_approved_figure_number_and_page_are_resolved(self):
        figure=get_figure('image-07-9007')
        self.assertEqual(figure.label,'图7.19')
        self.assertEqual(figure.section_id,7)
        source=TextbookChunk(figure.source,'7.3.1欧拉图及欧拉路径','图7.19',frozenset(),asset_ids=(figure.id,),chapter_id=7,section_id=7)
        self.assertEqual(retrieve_figures('图7.19',[source])[0].id,figure.id)
        refs=complete_pdf_references([source],'图7.19[1]',[],figures=[figure])
        self.assertEqual(refs[0]['label'],'图7.19')
        self.assertEqual(refs[0]['selection_ref']['rects'][0]['page'],15)
    def test_unapproved_or_stale_figure_mapping_is_not_applied(self):
        import json,tempfile
        from pathlib import Path
        from unittest.mock import patch
        from knowledge.figure_locations import apply_figure_location, LOCATIONS
        original=get_figure('image-07-9007')
        raw=replace(original,label='未核定对象',section_id=0,kind='image',selection_ref=None)
        item=json.loads(LOCATIONS.read_text(encoding='utf8'))[0]
        for change in ({'asset_sha256':'0'*64},{'version':'0'*64},{'review_status':'pending'},{'section_id':99}):
            with tempfile.TemporaryDirectory() as directory:
                file=Path(directory)/'mapping.json';file.write_text(json.dumps([item|change]),encoding='utf8')
                with patch('knowledge.figure_locations.LOCATIONS',file):
                    located=apply_figure_location(raw)
                self.assertEqual(located.label,'未核定对象')
                self.assertIsNone(located.selection_ref)
