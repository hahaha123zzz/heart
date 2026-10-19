import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import fitz
from knowledge.proof_units import units_for, dependencies, expand_proof_sources, focus_pages, _scan, REF
from knowledge.textbook import TextbookChunk
from agents.quality_checker import QualityChecker
from agents.teaching_planner import TeachingPlan
from agents.response_generator import requests_proof_overview

class ProofUnitTests(unittest.TestCase):
    def source(self,label='定理8.11',**changes):
        unit=units_for(8)[label]
        data=dict(source='第8章特殊图（新）.txt',section=unit.section['title'],text=label+' 原始召回正文',
                  terms=frozenset(),chapter_id=8,section_id=unit.section['id'],kind='text',chunk_id='recalled')
        return TextbookChunk(**(data|changes))
    def test_cross_section_prerequisite_and_exercise_boundary(self):
        unit=units_for(8)['定理8.11']
        linked,unresolved=dependencies(unit)
        self.assertEqual(unit.pages,[12,13])
        self.assertIn('归纳完成',unit.text)
        self.assertNotIn('练习8.2',unit.text)
        self.assertEqual([u.label for u in linked],['定理8.9'])
        self.assertEqual(linked[0].pages,[10])
        cross=units_for(7)['定理7.7']
        prior,_=dependencies(cross)
        self.assertEqual(prior[0].label,'定理7.2')
        self.assertNotEqual(prior[0].section['id'],cross.section['id'])
        self.assertEqual(unresolved,[])
    def test_cross_section_public_references_preserve_source_numbers_and_pages(self):
        unit=units_for(7)['定理7.7']
        source=TextbookChunk(source='第7章图（新）.txt',section=unit.section['title'],text='定理7.7 召回正文',terms=frozenset(),chapter_id=7,section_id=unit.section['id'],chunk_id='recalled')
        sources,bundle=expand_proof_sources([source, self.source(text='其他背景')],'解释定理7.7的证明，指出前置定理')
        refs=bundle.public_references(sources)
        self.assertEqual([r['source_index'] for r in refs],[0,2])
        self.assertEqual([r['selection_ref']['rects'][0]['page'] for r in refs],[10,4])
        self.assertEqual(refs[1]['label'],'定理7.2')
        self.assertEqual(refs[1]['selection_ref']['section_id'],units_for(7)['定理7.2'].section['id'])
        self.assertTrue(refs[1]['selection_ref']['image_refs'])

    def test_recovered_numbered_units_get_distinct_pdf_references(self):
        unit=units_for(7)['定理7.1']
        source=TextbookChunk(source='第7章图（新）.txt',section=unit.section['title'],text='定理7.1 原始召回',terms=frozenset(),chapter_id=7,section_id=unit.section['id'],chunk_id='primary')
        sources,bundle=expand_proof_sources([source],'根据定理7.1证明这个结论是否成立')
        for label in ('定义7.18','定理7.11'):
            extra=units_for(7)[label]
            sources.append(TextbookChunk(source='第7章图（新）.txt',section=extra.section['title'],text=label+' 补检索正文',terms=frozenset(),chapter_id=7,section_id=extra.section['id'],chunk_id='recovered-'+label))
        refs=bundle.public_references(sources)
        self.assertEqual([r['source_index'] for r in refs],[0,1,2])
        self.assertEqual([r['label'] for r in refs],['定理7.1','定义7.18','定理7.11'])
        self.assertEqual([r['selection_ref']['rects'][0]['page'] for r in refs],[3,14,14])
        self.assertEqual(bundle.public()['prerequisites'],[])
        bad=sources[-1].__class__(**(sources[-1].__dict__|{'source':'另一教材.txt'}))
        self.assertEqual([r['label'] for r in bundle.public_references(sources[:-1]+[bad])],['定理7.1','定义7.18'])

    def test_no_borrowed_forward_reference(self):
        unit=units_for(8)['定理8.16']
        linked,unresolved=dependencies(unit)
        self.assertEqual([u.label for u in linked],['定理8.14'])
        self.assertIn('定理9.15',unresolved)
        self.assertTrue(unit.omitted)
    def test_expansion_has_complete_body_separate_citation_and_two_images(self):
        sources,bundle=expand_proof_sources([self.source()],'解释定理8.11完整证明')
        self.assertIsNotNone(bundle)
        self.assertIn('归纳完成',sources[0].text)
        self.assertIn('定理8.9',sources[1].text)
        self.assertEqual(sources[1].page,10)
        self.assertEqual(len(bundle.supplement.images),2)
        self.assertEqual(bundle.public()['relation_type'],'explicit_citation_not_mathematically_verified')
    def test_omitted_step_is_not_presented_as_book_proof(self):
        sources,bundle=expand_proof_sources([self.source('定理8.16')],'证明定理8.16（3）⇒（4）')
        self.assertIsNotNone(bundle)
        self.assertIn('补充推导必须与原文区分',sources[0].text)
        self.assertEqual(bundle.supplement.pages,[15])
    def test_wrong_section_or_file_cannot_expand(self):
        for changes in ({'section':'另一小节'},{'section_id':99},{'source':'另一教材.txt'}):
            source=self.source(**changes)
            result,bundle=expand_proof_sources([source],'解释定理8.11')
            self.assertIsNone(bundle)
            self.assertEqual(result,[source])
    def test_background_reference_not_eligible(self):
        source=self.source(text='由定理8.11可知一些结果')
        self.assertIsNone(expand_proof_sources([source],'解释定理8.11')[1])
    def test_multiple_requested_theorems_do_not_silently_choose_one(self):
        self.assertIsNone(expand_proof_sources([self.source()],'比较证明定理8.11和定理8.9')[1])
    def test_unknown_number_does_not_expand(self):
        self.assertIsNone(expand_proof_sources([self.source(text='定理8.999 正文')],'解释定理8.999')[1])
    def test_hash_failure_preserves_source(self):
        source=self.source()
        with patch('knowledge.proof_units.units_for',side_effect=ValueError('版本错误')):
            result,bundle=expand_proof_sources([source],'解释定理8.11')
        self.assertEqual(result,[source]);self.assertIsNone(bundle)
    def test_comment_not_new_theorem_heading(self):
        unit=units_for(10)['定理10.7']
        self.assertIn('规范映射',unit.text)
        self.assertNotIn('定理 10.8',unit.text)
    def test_letter_suffix_is_not_a_complete_reference(self):
        self.assertIsNone(REF.search("定理10.2l"))
        self.assertEqual(REF.search("定理10.21")[3],"21")
    def test_half_proof_omission_is_visible(self):
        self.assertTrue(units_for(7)["定理7.13"].omitted)
    def test_focus_on_second_page_step(self):
        query="定理8.11为什么红黄通路存在时黑白顶点在不同连通分支，解释这一步"
        self.assertEqual(focus_pages(units_for(8)["定理8.11"],query),[13])
    def test_proof_overview_length_does_not_break_quality_gate(self):
        plan=TeachingPlan(goal="证明路线",strategy="worked_example",action="explain",difficulty="medium")
        self.assertTrue(requests_proof_overview("解释完整证明思路"))
        response="归纳与分情况证明。"*35
        self.assertEqual(QualityChecker._rule_check(response,plan,{"proof_overview":True}),[])
        self.assertTrue(QualityChecker._rule_check(response,plan,{}))
        self.assertFalse(requests_proof_overview("解释这一步"))
    def test_explicit_direction_focus(self):
        self.assertEqual(focus_pages(units_for(8)['定理8.16'],'解释（1）⇒（2）'),[15])
    def test_three_page_proof_is_retained_with_bounded_visual_window(self):
        # 合成版式验证三页能力；实际教材诊断不冒充三页样本。
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'test.pdf'
            pdf=fitz.open()
            for text in ('THEOREM1.1 statement proof begin','proof middle step','proof final conclusion'):
                page=pdf.new_page();page.insert_text((80,110),text)
            pdf.save(target);pdf.close()
            record=dict(chapter_id=1,version=hashlib.sha256(target.read_bytes()).hexdigest(),page_count=3,
                        sections=[dict(id=1,title='合成小节',page=1,y=.08,verified=True)])
            def lines(page):
                n=page.number+1
                text='定理1.1 开始证明' if n==1 else '证明中间步骤' if n==2 else '证明最终结论'
                return [(.13,text,{})]
            with patch('knowledge.proof_units.document_for_chapter',return_value=record),patch('knowledge.proof_units.pdf_path',return_value=target),patch('knowledge.proof_units._lines',side_effect=lines):
                unit=units_for(1)['定理1.1']
                self.assertEqual(unit.pages,[1,2,3]);self.assertIn('最终结论',unit.text)
                self.assertEqual(len(focus_pages(unit,'完整证明')),2)
                self.assertFalse(unit.truncated)
            _scan.cache_clear()

if __name__=='__main__':unittest.main()
