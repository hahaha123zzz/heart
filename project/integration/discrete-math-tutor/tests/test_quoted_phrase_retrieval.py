import unittest
from unittest.mock import patch

from knowledge.hybrid_retrieval import INDEX, retrieve_hybrid
from knowledge.textbook import load_textbook


@unittest.skipUnless(INDEX.is_file(), "retrieval index is not built")
class QuotedPhraseRetrievalTests(unittest.TestCase):
    def test_exact_example_outranks_generic_terms_with_or_without_quotes(self):
        for question, expected in (
            ("问“北京大学全体学生”这一集合的对象是谁", "北京大学全体学生"),
            ("问“全体正整数”的组成对象是谁", "全体正整数"),
            ("问全体正整数的组成对象是谁", "全体正整数"),
        ):
            with self.subTest(question=question), patch("knowledge.hybrid_retrieval.INDEX", INDEX):
                hits = retrieve_hybrid(question, load_textbook(), limit=2)
            self.assertTrue(hits)
            self.assertEqual(hits[0].section, "1.1.1集合及其元素")
            self.assertIn(expected, hits[0].text)


if __name__ == "__main__":
    unittest.main()
