"""相关性门槛之后，明确概念不能被跨小节多样性挤掉关键定理。"""
import unittest
from unittest.mock import patch
from knowledge.hybrid_retrieval import _select_ranked
from knowledge.concept_aliases import expand_query, matched_aliases


def row(identifier, text, section, kind='text', section_id=7):
    return {'id':identifier,'text':text,'section':section,'chapter_id':7,'section_id':section_id,
            'parent_id':identifier,'kind':kind}


class ConceptEvidenceTests(unittest.TestCase):
    def select(self, rows, *, aliases=('欧拉回路','欧拉图'), refs=()):
        from knowledge.textbook import TextbookChunk
        with patch('knowledge.hybrid_retrieval._expand_parent',side_effect=lambda db,r:r['text']), \
             patch('knowledge.hybrid_retrieval._as_chunk',side_effect=lambda r,**kw:TextbookChunk('教材',r['section'],kw['text'],frozenset(),chunk_id=r['id'],chapter_id=7)):
            return [chunk.chunk_id for chunk in _select_ranked(None,[(10-i,r) for i,r in enumerate(rows)],frozenset(),2,
                cross_chapter=True,focus_aliases=aliases,refs=set(refs))]

    def test_circuit_theorem_not_displaced_by_drawing_or_other_section(self):
        rows=[row('drawing','邻近证明文本','第7章教材绘图','image_context',None),
              row('open','定理7.12 连通且恰有两个奇度顶点','7.3.1欧拉图及欧拉路径'),
              row('other','定义7.9 路径','7.2.1路径与回路',section_id=5),
              row('circuit','定理7.11 连通且所有顶点偶数度','7.3.1欧拉图及欧拉路径')]
        self.assertEqual(self.select(rows),['open','circuit'])

    def test_explicit_number_retains_priority(self):
        rows=[row('open','定理7.12 条件','7.3.1欧拉图及欧拉路径'),
              row('circuit','定理7.11 条件','7.3.1欧拉图及欧拉路径'),
              row('explicit','定理7.4 路径性质','7.2.1路径与回路',section_id=5)]
        self.assertEqual(self.select(rows,refs=['定理7.4']),['explicit','open'])

    def test_absent_or_unstructured_theorem_not_invented(self):
        rows=[row('drawing','定理7.11 邻近文本','第7章教材绘图','image_context',None),
              row('other','定义7.9 路径','7.2.1路径与回路',section_id=5)]
        self.assertEqual(self.select(rows),['drawing','other'])

    def test_open_path_not_expanded_as_circuit(self):
        self.assertIn('欧拉图',expand_query('欧拉回路的存在条件'))
        self.assertEqual(matched_aliases('欧拉路径的存在条件'),[])


if __name__=='__main__':unittest.main()
