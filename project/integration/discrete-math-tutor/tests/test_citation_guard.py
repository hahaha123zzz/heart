import unittest
from knowledge.citation_guard import citation_issues


class CitationGuardTests(unittest.TestCase):
    excerpts = '[1] 教材｜欧拉图\n定理7.12 欧拉路径条件\n\n[2] 教材｜欧拉图\n定理7.11 欧拉图条件'

    def test_mismatched_theorem_rejected_with_correct_index(self):
        issues = citation_issues('按定理7.11[1]有欧拉回路。', self.excerpts)
        self.assertEqual(len(issues), 1)
        self.assertIn('摘录[2]', issues[0])

    def test_correct_theorem_reference_passes(self):
        self.assertEqual(citation_issues('按定理7.11[2]有欧拉回路。', self.excerpts), [])

    def test_invalid_index_rejected(self):
        self.assertTrue(citation_issues('定理7.11[3]', self.excerpts))

    def test_normal_text_citation_not_assigned_theorem(self):
        self.assertEqual(citation_issues('四个顶点的度均为偶数[2]。', self.excerpts), [])

    def test_spacing_and_fullwidth_dot(self):
        self.assertEqual(citation_issues('定理 7．11（[2]）', self.excerpts), [])
