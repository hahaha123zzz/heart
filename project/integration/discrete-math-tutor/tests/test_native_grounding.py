from contextlib import closing
"""真实教材块与 PDF 的来源发布回归，不使用模型或替身检索结果。"""
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from copy import deepcopy
from knowledge.course_config import PSYCHOLOGY_DIR
from integrations.deeptutor.native_grounding import prepare_retrieval
from integrations.deeptutor.native_delivery import publication_sources


class NativeGroundingTests(unittest.TestCase):
    def setUp(self):
        from knowledge.hybrid_retrieval import _as_chunk
        from deeptutor.core.context import UnifiedContext
        path=PSYCHOLOGY_DIR/'rag_index.sqlite3'
        if not path.is_file():self.skipTest('需要本机正式教材索引')
        with closing(sqlite3.connect(path)) as db:
            db.row_factory=sqlite3.Row
            self.chunk=_as_chunk(db.execute("SELECT * FROM chunks WHERE chapter_id=2 AND text LIKE '%自变量%' ORDER BY length(text) DESC LIMIT 1").fetchone())
        self.context=UnifiedContext()
    def test_repeated_retrieval_keeps_stable_indices_after_selection_offset(self):
        self.context.metadata['_heart_citation_offset']=2
        first=prepare_retrieval('自变量是什么',[self.chunk],self.context,'实验心理学')
        second=prepare_retrieval('自变量是什么',[self.chunk],self.context,'实验心理学')
        self.assertTrue(first)
        self.assertEqual(first[0]['index'],3)
        self.assertEqual([s['index'] for s in first],[s['index'] for s in second])
        self.assertEqual(self.context.metadata['source_index'][first[0]['rag_source_id']],self.chunk.text)
    def test_quote_reaches_real_pdf_publication_without_relaxing_checks(self):
        from models.chat_request import ChatRequest
        from agents.agent_loop import LoopResult
        from agents.agent_loop_service import _publish_gate
        from agents.q3_navigation import LearningTarget
        sources=prepare_retrieval('自变量是什么',[self.chunk],self.context,'实验心理学')
        text=sources[0]['text']+'[1]'
        result=LoopResult(final_text=text,completed=True,sources=sources)
        # 此测试核验当前 PDF/原文/坐标；全课程资源清单已有独立验收，避免每次扫描全部媒体。
        with patch('knowledge.course_release.binding',return_value={'release_id':'test','status':'test','ready':False}):
            accepted,reason=_publish_gate(SimpleNamespace(),ChatRequest(message='自变量是什么'),
                LearningTarget('audit','变量'),allow_model_knowledge=True)(text,result)
        self.assertTrue(accepted,reason)
        self.assertTrue(result._publication['pdf_references'])
    def test_changed_versions_and_conflicting_indices_are_rejected(self):
        rows=prepare_retrieval('自变量是什么',[self.chunk],self.context,'实验心理学')
        versions={row['document_id']:row['version'] for row in rows}
        self.assertTrue(publication_sources({}, {'sources':rows+rows},versions))
        with self.assertRaises(ValueError):publication_sources({}, {'sources':rows},{})
        bad=deepcopy(rows[0]);bad['source_id']='forged'
        with self.assertRaises(ValueError):publication_sources({}, {'sources':rows+[bad]},versions)
