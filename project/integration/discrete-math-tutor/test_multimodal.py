"""验证真实教材中的多模态检索和图片输入。"""
import unittest
from knowledge.textbook import load_textbook, retrieve
from knowledge.figures import retrieve_figures, get_figure
from llm.client import LLMClient

class MultimodalTests(unittest.TestCase):
    def test_absolute_value_table_preserves_values(self):
        sources = retrieve('绝对值函数的表格', load_textbook(), limit=2)
        self.assertEqual(sources[0].kind, 'table')
        self.assertIn('| f(x) | 3 | 2 | 1 | 0 | 1 | 2 | 3 |', sources[0].text)

    def test_binomial_formula_attaches_original_images(self):
        query='请引用教材原公式，解释牛顿二项式定理公式中的C(n,k)'
        sources=retrieve(query,load_textbook(),limit=2)
        self.assertEqual(sources[0].kind,'formula')
        figures=retrieve_figures(query,sources)
        self.assertEqual([f.id for f in figures], ['formula-03-0118','formula-03-0119'])
        request=LLMClient._with_images([dict(role='user',content=query)],[f.path for f in figures])
        self.assertEqual(len(request[-1]['content']),3)
        self.assertTrue(all(f.is_valid() for f in figures))

    def test_special_graph_image_is_not_forced_into_chapter_seven(self):
        query='特殊图的完全匹配配图'
        sources=retrieve(query,load_textbook(),limit=2)
        self.assertTrue(sources[0].source.startswith('第8章'))
        figures=retrieve_figures(query,sources)
        self.assertTrue(figures)
        self.assertTrue(all(f.chapter_id==8 for f in figures))
        self.assertTrue(all('图号未核定' in f.caption for f in figures))
        self.assertEqual(get_figure(figures[0].id),figures[0])

    def test_basic_concept_does_not_attach_unrelated_formula(self):
        query='集合是什么'
        self.assertEqual(retrieve_figures(query,retrieve(query,load_textbook(),limit=2)),[])

if __name__=='__main__':
    unittest.main()
