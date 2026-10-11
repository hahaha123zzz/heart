import unittest
from knowledge.logic_formula import parse, template, extract, search_text
from knowledge.concept_aliases import expand_query, matched_aliases

class FormulaTests(unittest.TestCase):
    def test_variable_renaming(self):
        self.assertEqual(template(parse("A∧B")), template(parse(r"p\land q")))
    def test_repeated_variable_is_preserved(self):
        self.assertNotEqual(template(parse("p∧p")), template(parse("A∧B")))
    def test_negation_scope(self):
        self.assertNotEqual(template(parse("¬(p∧q)")), template(parse("¬p∧q")))
    def test_precedence(self):
        self.assertEqual(parse("p∨q∧r"), parse("p∨(q∧r)"))
    def test_right_associative_implication(self):
        self.assertEqual(parse("p→q→r"), parse("p→(q→r)"))
    def test_template_does_not_prove_equivalence(self):
        self.assertEqual(template(parse("A→B")), template(parse("B→A")))
        self.assertNotEqual(parse("A→B"), parse("B→A"))
    def test_reject_malformed_and_unsupported(self):
        for text in ("p∧", "p∧q)", "(p∧q", "p=q", "∀p(p∧q)", r"p\landscape q"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse(text)
    def test_legacy_negation_and_constants(self):
        self.assertEqual(parse("┐p"), parse(r"\neg p"))
        self.assertNotEqual(template(parse("p∧0")), template(parse("p∧1")))
    def test_extract_separate_expressions(self):
        self.assertEqual([x[0] for x in extract("表头 | p | q | p∧q |\n以及┐p表示否定")], ["p∧q", "¬p"])
    def test_alias_is_whole_concept(self):
        self.assertIn("序偶", expand_query("有序对是什么？"))
        self.assertFalse(matched_aliases("序关系是什么？"))

    def test_search_text_preserves_shared_bindings(self):
        self.assertEqual(search_text("A→B 与 B→A 相同吗？"), "p→q 与 q→p 相同吗？")
        self.assertEqual(search_text("¬Z 与 Z 的真值"), "¬p 与 p 的真值")
        self.assertEqual(search_text("p∧p 在 Python 中"), "p∧p 在 Python 中")
