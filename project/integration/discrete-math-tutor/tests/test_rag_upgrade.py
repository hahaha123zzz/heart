"""教材结构索引与检索入口的回归检查。"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from array import array
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from knowledge import hybrid_retrieval
from agents.question_designer import QuestionOption, QuestionSpec
from agents.response_generator import ResponseGenerator
from knowledge.structured_index import build_records
from knowledge.textbook import load_textbook
from orchestrator import TutorOrchestrator
from scripts.build_rag_index import build_index


class RagUpgradeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rerank_env = patch.dict(os.environ, {"RAG_RERANK_MODEL": ""})
        cls.rerank_env.start()
        cls.records = build_records()
        cls.temp = tempfile.TemporaryDirectory()
        cls.index = Path(cls.temp.name) / "rag.sqlite3"
        build_index(cls.index)
        cls.old_index = hybrid_retrieval.INDEX
        hybrid_retrieval.INDEX = cls.index
        cls.old_chunks = load_textbook()

    @classmethod
    def tearDownClass(cls):
        hybrid_retrieval.INDEX = cls.old_index
        cls.temp.cleanup()
        cls.rerank_env.stop()

    def test_quality_issue_cannot_be_marked_passed(self):
        from agents.quality_checker import QualityChecker
        from agents.teaching_planner import TeachingPlan
        from models.student_state import StudentState
        llm=SimpleNamespace(chat_json=lambda *args,**kwargs: {"passed":True,"issues":["证明引用了待证定理，存在循环论证"],"suggestions":"使用已知树定理"})
        result=QualityChecker(llm).check("由待证定理的等价关系立得",StudentState(student_id="quality-regression",current_concept="树"),TeachingPlan(goal="证明树的等价定义",strategy="worked_example",action="explain",difficulty="medium",hint_level=1,expected_student_behavior="理解证明",rationale="解释"),"如何证明？")
        self.assertFalse(result.passed)
        self.assertIn("循环论证",result.issues[0])
        self.assertEqual(result.suggestions,"使用已知树定理")

    def test_named_theorem_body_beats_formula_background(self):
        fake=SimpleNamespace(rerank=lambda query,passages,batch_size: [8.0 if "公式" in p else 2.0 for p in passages])
        trace={}
        with patch.dict(os.environ,{"RAG_RERANK_MODEL":"test"}), patch.object(hybrid_retrieval,"_reranker",return_value=("fastembed",fake)):
            hits=hybrid_retrieval.retrieve_hybrid("请解释定理8.15的反证",self.old_chunks,limit=2,trace=trace)
        self.assertEqual(hits[0].kind,"text")
        self.assertTrue(hits[0].text.startswith("定理8.15"))
        self.assertIsNotNone(hits[0].section_id)

    def test_background_reference_is_not_primary_unit(self):
        row={"kind":"text","section_id":7,"text":"由定理8.15可知结论。"}
        self.assertFalse(hybrid_retrieval._primary_unit(row,{"定理8.15"}))
        row["text"]="定理8.150 另一个不同编号。"
        self.assertFalse(hybrid_retrieval._primary_unit(row,{"定理8.15"}))
        row["text"]="定理8.15 任何不少于两个顶点的树都至少有两片叶。"
        self.assertTrue(hybrid_retrieval._primary_unit(row,{"定理8.15"}))

    def test_task_preference_does_not_bypass_reranker_gate(self):
        fake = SimpleNamespace(rerank=lambda query, passages, batch_size: [-100.0] * len(passages))
        with patch.dict(os.environ, {"RAG_RERANK_MODEL": "test"}), patch.object(hybrid_retrieval, "_reranker", return_value=("fastembed", fake)):
            self.assertEqual(hybrid_retrieval.retrieve_hybrid("集合包含哪些元素？", self.old_chunks,
                            preferred_types=("definition", "example")), [])

    def test_task_preference_preserves_exact_theorem_and_location(self):
        trace = {}
        hits = hybrid_retrieval.retrieve_hybrid("定理7.4如何证明？", self.old_chunks, limit=2,
                    preferred_types=("example",), trace=trace)
        self.assertTrue(hits[0].text.startswith("定理7.4"))
        self.assertEqual(hits[0].page, 7)
        self.assertEqual(trace["task_ranking"]["preferred_types"], ["example"])

    def test_empty_task_preference_is_backward_compatible(self):
        original = hybrid_retrieval.retrieve_hybrid("鸽笼原理怎样理解？", self.old_chunks)
        explicit = hybrid_retrieval.retrieve_hybrid("鸽笼原理怎样理解？", self.old_chunks, preferred_types=())
        self.assertEqual(original, explicit)

    def test_subset_symbol_expands_verified_textbook_terms(self):
        from knowledge.concept_aliases import expand_query
        expanded=expand_query('A⊆B 且 B⊆C')
        self.assertIn('子集合',expanded)
        self.assertIn('包含于',expanded)
        self.assertTrue(expanded.startswith('A⊆B 且 B⊆C'))

    def test_renamed_formula_selects_structural_table(self):
        fake = SimpleNamespace(rerank=lambda query, passages, batch_size: [2.0] * len(passages))
        trace = {}
        with patch.dict(os.environ, {"RAG_RERANK_MODEL": "test"}), patch.object(hybrid_retrieval, "_reranker", return_value=("fastembed", fake)):
            hits = hybrid_retrieval.retrieve_hybrid("X∧Y 什么时候为真？", self.old_chunks, limit=2, trace=trace)
        self.assertTrue(trace["structural_table_match"])
        self.assertFalse(trace["exact_resource"])
        self.assertEqual(hits[0].kind, "table")
        self.assertIn("| p | q | p∧q |", hits[0].text)

    def test_formula_structure_cannot_bypass_evidence_gate(self):
        fake = SimpleNamespace(rerank=lambda query, passages, batch_size: [-100.0] * len(passages))
        with patch.dict(os.environ, {"RAG_RERANK_MODEL": "test"}), patch.object(hybrid_retrieval, "_reranker", return_value=("fastembed", fake)):
            self.assertEqual(hybrid_retrieval.retrieve_hybrid("X∧Y 什么时候为真？", self.old_chunks), [])

    def test_theorem_and_proof_keep_one_parent(self):
        hit = next(item for item in self.records
                   if item["kind"] == "text" and item["chapter_id"] == 7
                   and "定理7.4" in item["text"])
        self.assertIn("证", hit["text"])
        self.assertEqual(hit["section"], "7.2.1  路径与回路")
        self.assertEqual(hit["page"], 7)

    def test_exercises_are_not_indexed(self):
        catalog = json.loads((Path(__file__).resolve().parents[1] / "knowledge" / "exercises" / "catalog.json").read_text(encoding="utf-8"))
        first = catalog["questions"][0]
        indexes = {block["block_index"] for block in first["blocks"]}
        self.assertFalse(any(item["chapter_id"] == 1 and item["block_start"] in indexes
                             for item in self.records))

    def test_exact_theorem_and_table_retrieval(self):
        theorem = hybrid_retrieval.retrieve_hybrid("定理7.4如何证明？", self.old_chunks, limit=2)
        self.assertEqual(theorem[0].chapter_id, 7)
        self.assertIn("定理7.4", theorem[0].text)
        table = hybrid_retrieval.retrieve_hybrid("根据绝对值函数的表格，x=-3时f(x)是多少？", self.old_chunks, limit=2)
        self.assertEqual(table[0].kind, "table")
        self.assertIn("| f(x) | 3 |", table[0].text)

    def test_unmentioned_definition_has_no_textbook_hit(self):
        self.assertEqual(
            hybrid_retrieval.retrieve_hybrid("对称差是什么？", self.old_chunks, limit=2),
            [],
        )

    def test_expression_uses_exact_table_header(self):
        hits = hybrid_retrieval.retrieve_hybrid(
            "查真值表：p→q 在哪种赋值下为假？", self.old_chunks, limit=2,
        )
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].kind, "table")
        self.assertIn("| p | q | p→q |", hits[0].text)

    def test_verified_figure_beats_unverified_drawing_context(self):
        hits = hybrid_retrieval.retrieve_hybrid(
            "图 7.20 中的粗线表示什么？", self.old_chunks, limit=2,
        )
        self.assertEqual(hits[0].kind, "image_context")
        self.assertIn("哈密顿回路", hits[0].text)
        self.assertFalse(any("图号未核定" in hit.text for hit in hits))

    def test_section_concepts_beat_unrelated_definition_or_formula(self):
        for query, section in (
            ("存在量词的辖域是什么意思？", "量词及其辖域"),
            ("如何把谓词公式改写为前束范式？", "谓词公式的前束范式"),
        ):
            with self.subTest(query=query):
                hits = hybrid_retrieval.retrieve_hybrid(query, self.old_chunks, limit=2)
                self.assertIn(section, hits[0].section)

    def test_low_similarity_question_has_no_evidence(self):
        class UnrelatedEmbedder:
            def embed(self, _questions):
                return iter([[1.0, 0.0]])

        with patch.object(hybrid_retrieval, "_vectors", return_value=(
            "test", [("unrelated", array("f", [0.0, 1.0]), 1.0)],
        )), patch.object(hybrid_retrieval, "_embedder", return_value=UnrelatedEmbedder()):
            self.assertEqual(hybrid_retrieval.retrieve_hybrid(
                "RSA 公钥算法的密钥怎样生成？", self.old_chunks, limit=2,
            ), [])

    def test_reranker_can_recover_low_dense_evidence(self):
        class WeakEmbedder:
            def embed(self, _questions):
                return iter([[1.0, 0.0]])

        class EvidenceReranker:
            def rerank(self, query, passages, **kwargs):
                return [8.0 if "并集（union" in passage else -8.0 for passage in passages]

        trace = {}
        with patch.dict(os.environ, {"RAG_RERANK_MODEL": "BAAI/bge-reranker-base"}), \
             patch.object(hybrid_retrieval, "_vectors", return_value=(
                 "test", [("ch1-b169-0", array("f", [0.0, 1.0]), 1.0)],
             )), patch.object(hybrid_retrieval, "_embedder", return_value=WeakEmbedder()), \
             patch.object(hybrid_retrieval, "_reranker", return_value=("fastembed", EvidenceReranker())):
            hits = hybrid_retrieval.retrieve_hybrid(
                "集合的交集与并集有什么区别？", self.old_chunks, trace=trace,
            )
        self.assertTrue(hits)
        self.assertIn("并、交、差、补运算", hits[0].section)
        self.assertEqual(trace["evidence_gate"], "reranker")

    def test_reranker_rejects_all_candidates_without_tail_fallback(self):
        class UnrelatedReranker:
            def rerank(self, query, passages, **kwargs):
                return [-10.0 for _ in passages]

        trace = {}
        with patch.dict(os.environ, {"RAG_RERANK_MODEL": "BAAI/bge-reranker-base"}), \
             patch.object(hybrid_retrieval, "_reranker", return_value=("fastembed", UnrelatedReranker())):
            hits = hybrid_retrieval.retrieve_hybrid("集合包含哪些元素？", self.old_chunks, trace=trace)
        self.assertEqual(hits, [])
        self.assertEqual(trace["rejection"], "reranker_threshold")

    def test_resource_reference_matches_complete_number(self):
        self.assertFalse(hybrid_retrieval._reference_present("见图7.20", {"图7.2"}))
        self.assertTrue(hybrid_retrieval._reference_present("见图 7.20", {"图7.20"}))

    def test_unknown_reference_cannot_bypass_reranker_gate(self):
        class UnrelatedReranker:
            def rerank(self, query, passages, **kwargs):
                return [-10.0 for _ in passages]

        with patch.dict(os.environ, {"RAG_RERANK_MODEL": "BAAI/bge-reranker-base"}), \
             patch.object(hybrid_retrieval, "_reranker", return_value=("fastembed", UnrelatedReranker())):
            self.assertEqual(hybrid_retrieval.retrieve_hybrid(
                "图99.99展示了什么集合？", self.old_chunks,
            ), [])

    def test_invalid_reranker_scores_record_fallback(self):
        class InvalidReranker:
            def rerank(self, query, passages, **kwargs):
                return [float("nan")]

        trace = {}
        with patch.dict(os.environ, {"RAG_RERANK_MODEL": "BAAI/bge-reranker-base"}), \
             patch.object(hybrid_retrieval, "_reranker", return_value=("fastembed", InvalidReranker())):
            hits = hybrid_retrieval.retrieve_hybrid("鸽笼原理怎样理解？", self.old_chunks, trace=trace)
        self.assertTrue(hits)
        self.assertEqual(trace["evidence_gate"], "fallback")
        self.assertIn("invalid scores", trace["reranker_error"])

    def test_lexical_only_index_requires_evidence(self):
        for question in ("RSA 公钥算法的密钥怎样生成？", "梯度下降怎样训练神经网络？"):
            with self.subTest(question=question):
                self.assertEqual(hybrid_retrieval.retrieve_hybrid(
                    question, self.old_chunks, limit=2,
                ), [])
        self.assertIn("鸽笼原理", hybrid_retrieval.retrieve_hybrid(
            "鸽笼原理怎样理解？", self.old_chunks, limit=2,
        )[0].section)
        self.assertEqual(hybrid_retrieval.retrieve_hybrid(
            "p→q", self.old_chunks, limit=2,
        )[0].chapter_id, 4)

    def test_no_evidence_stops_before_teaching_pipeline(self):
        tutor = TutorOrchestrator.__new__(TutorOrchestrator)
        tutor.memory = MagicMock()
        tutor.memory.get_active_goal.return_value = "图的基本概念"
        tutor.memory.get_history.return_value = []
        tutor.memory.get_state.return_value.model_dump.return_value = {"mastery": 0.4}
        tutor.conversation_router = MagicMock()
        tutor.conversation_router.route.return_value = SimpleNamespace(
            intent="switch_topic", topic="RSA", confidence=0.9, status="ok",
            model_dump=lambda: {"intent": "switch_topic"},
        )
        tutor.response_generator = MagicMock()
        tutor.textbook_chunks = self.old_chunks
        with patch("orchestrator.retrieve_hybrid", return_value=[]) as retriever, \
             patch("orchestrator.retrieve_figures", return_value=[]):
            result = tutor.handle_turn("no-evidence-test", "RSA 密钥怎么生成？", account_type="test")
        self.assertEqual(retriever.call_args.args[0], "RSA 密钥怎么生成？")
        self.assertEqual(result["textbook_sources"], [])
        self.assertEqual(result["image_refs"], [])
        self.assertIn("没有检索到", result["reply"])
        tutor.response_generator.generate.assert_not_called()
        tutor.memory.set_active_goal.assert_not_called()

    def test_generated_multiple_choice_keeps_all_options(self):
        reply = "教材说明量词的辖域范围。" * 15 + "\nA. 第一项\nB. 第二项\nC. 第三项\nD. 第四项"
        self.assertGreater(len(reply), 200)
        llm = MagicMock()
        llm.chat.return_value = reply
        state = MagicMock()
        state.model_dump.return_value = {}
        plan = MagicMock()
        plan.strategy = "scaffolding"
        plan.model_dump.return_value = {}
        spec = QuestionSpec(stem="选出辖域", options=[
            QuestionOption(text=label) for label in ("第一项", "第二项", "第三项", "第四项")
        ])
        result = ResponseGenerator(llm).generate(state, plan, "什么是辖域？", [], spec)
        self.assertIn("D. 第四项", result)


if __name__ == "__main__":
    unittest.main()
