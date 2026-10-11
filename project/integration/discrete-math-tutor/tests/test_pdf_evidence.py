import unittest
from unittest.mock import patch
from knowledge.textbook import TextbookChunk
from knowledge.pdf_evidence import enrich_sources

class PdfEvidenceTests(unittest.TestCase):
    def source(self, **changes):
        data=dict(source='第1章集合代数(新).txt',section='1.2.3集合的笛卡儿积',
            text='定义1.9 设，为任意对象，称集合为二元有序组，或序偶（ordered pairs）。',terms=frozenset(),
            chapter_id=1,section_id=8,page=11,kind='formula',asset_ids=('formula-01-0100',))
        return TextbookChunk(**(data|changes))
    def test_restores_formula_and_next_page_explanation(self):
        sources, supplement=enrich_sources([self.source()])
        self.assertIsNotNone(supplement)
        self.assertIn('{{a}',sources[0].text.replace(' ',''))
        self.assertIn('区别',sources[0].text)
        self.assertIn('第一分量',sources[0].text)
        self.assertEqual(supplement.pages,[11,12])
        self.assertEqual(len(supplement.images),2)
        self.assertEqual(sources[0].page,11)
    def test_requested_set_formula_reads_definition_original_page(self):
        source=TextbookChunk(source='第1章集合代数(新).txt',section='1.1.3  外延性公理与子集合',
            text='定义1.3 集合A称为集合B的子集合，如果A的每一个元素都是B的元素。',terms=frozenset(),
            chapter_id=1,section_id=4,page=3)
        sources,supplement=enrich_sources([source],query='A⊆B')
        self.assertIsNotNone(supplement)
        self.assertIn('定理1.3',sources[0].text)
        self.assertEqual(supplement.pages,[3,4])
        self.assertNotIn('练习1.1',sources[0].text.replace(' ',''))
        self.assertNotIn('选择题',sources[0].text)

    def test_wrong_section_title_cannot_attach_pdf(self):
        source=self.source(section='9.3.1序关系')
        sources,supplement=enrich_sources([source])
        self.assertIsNone(supplement)
        self.assertEqual(sources,[source])
    def test_unknown_anchor_cannot_use_section_heading_as_formula(self):
        source=self.source(text='定义1.999 这段原文不存在于当前小节。')
        self.assertIsNone(enrich_sources([source])[1])
    def test_version_failure_keeps_original_evidence(self):
        source=self.source()
        with patch('knowledge.pdf_evidence.resolve_selection',side_effect=ValueError('教材文件已变化')):
            sources,supplement=enrich_sources([source])
        self.assertEqual(sources,[source])
        self.assertIsNone(supplement)
    def test_background_number_is_not_formula_anchor(self):
        source=self.source(text='公式所在段落：a+b。\n公式前文（仅提供背景）：定义1.9 设，为任意对象。')
        self.assertIsNone(enrich_sources([source])[1])
    def test_complete_table_is_not_augmented(self):
        source=self.source(kind='table',asset_ids=(),text='|p|q|p∧q|')
        self.assertIsNone(enrich_sources([source])[1])

    def table_source(self, **changes):
        data=dict(source='第4章逻辑代数（新）.txt',section='4.1.2  逻辑联结词',
            text='教材表格\n| p | q | pq |\n| 0 / 0 / 1 / 1 | 0 / 1 / 0 / 1 | 1 / 0 / 0 / 1 |\n邻近正文：双向蕴涵词的意义见表4.6。\n表4.6',
            terms=frozenset(),chapter_id=4,section_id=3,page=2,kind='table')
        return TextbookChunk(**(data|changes))
    def test_requested_table_uses_caption_actual_page(self):
        sources,supplement=enrich_sources([self.table_source()],query='解释教材表4.6')
        self.assertIsNotNone(supplement)
        self.assertEqual(sources[0].page,4)
        self.assertIn('表4.6',sources[0].text)
        self.assertIn('同真值',sources[0].text)
        self.assertEqual(supplement.pages,[4])
    def test_cross_page_table_keeps_last_row(self):
        source=self.table_source(text='教材表格\n| p | q | pq |\n表4.4',asset_ids=('formula-04-0004',))
        sources,supplement=enrich_sources([source],query='表4.4的末行')
        self.assertEqual(supplement.pages,[3,4])
        self.assertEqual(sources[0].page,3)
        # 后页开头保留最后一行，不能从表号后的例4.6开始裁剪。
        self.assertLess(supplement.reference['rects'][1]['y1'],.09)
    def test_missing_table_caption_keeps_original(self):
        source=self.table_source(text='教材表格\n表4.999')
        self.assertIsNone(enrich_sources([source],query='表4.999')[1])
    def test_requested_table_not_borrowed_from_another_source(self):
        self.assertIsNone(enrich_sources([self.table_source()],query='表4.9')[1])
    def proof_source(self, **changes):
        data=dict(source='第8章特殊图（新）.txt',section='8.3.1  树的基本概念',
            text='定理8.16 T无回路且m=n−1。证反设T有k个连通分支（k≥2），显然',
            terms=frozenset(),chapter_id=8,section_id=7,page=14)
        return TextbookChunk(**(data|changes))
    def test_named_proof_recovers_continuation_without_asset_ids(self):
        sources,supplement=enrich_sources([self.proof_source()],query='解释定理8.16的（1）到（2）')
        self.assertIsNotNone(supplement)
        self.assertEqual(supplement.pages,[15])
        self.assertIn('矛盾。因此T 连通',sources[0].text)
        self.assertIn('mi',sources[0].text.replace(' ',''))
        self.assertNotIn('生成树',sources[0].text)
    def test_cross_page_proof_stops_before_next_theorem(self):
        source=self.proof_source(text='定理8.15 任何不少于两个顶点的树都至少有两片叶。证设T中至多只有一个顶点是叶，那么')
        sources,supplement=enrich_sources([source],query='解释定理8.15的反证')
        self.assertIsNotNone(supplement)
        self.assertEqual(supplement.pages,[14,15])
        self.assertIn('至少有两片叶',sources[0].text)
        self.assertNotIn('定理8.16',sources[0].text)
    def test_inline_theorem_reference_is_not_a_numbered_unit_anchor(self):
        source=self.proof_source(section='8.3.2 生成树',section_id=8,text='算法产生的图无回路，据定理8.16此图为树。')
        self.assertIsNone(enrich_sources([source],query='解释定理8.16的证明')[1])

if __name__=='__main__': unittest.main()
