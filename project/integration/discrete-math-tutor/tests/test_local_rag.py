"""真实LlamaIndex/BM25/RRF与只读索引；替换向量模型，禁止联网模型调用。"""
from array import array
from contextlib import closing, contextmanager
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from llama_index.core import VectorStoreIndex
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode
from knowledge.local_rag import course_retrieval as local
from knowledge.local_rag.config import RetrievalConfig
from knowledge.local_rag.rerank import clear_reranker_cache, rerank_nodes
from knowledge.local_rag.retrievers import build_retriever
from knowledge.local_rag.tokenization import ChineseBM25Retriever


class LocalRetrievalTests(unittest.TestCase):
    @contextmanager
    def database(self):
        with closing(sqlite3.connect(self.path)) as db:
            with db: yield db

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'rag_index.sqlite3'
        with self.database() as db:
            db.executescript('''CREATE TABLE metadata(key TEXT,value TEXT);
                CREATE TABLE vectors(id TEXT PRIMARY KEY,data BLOB);
                CREATE TABLE chunks(id TEXT PRIMARY KEY,source TEXT,section TEXT,text TEXT,
                kind TEXT,asset_ids TEXT,section_id INTEGER,parent_id TEXT,chapter_id INTEGER,
                page INTEGER,block_start INTEGER,block_end INTEGER);''')
            db.execute('INSERT INTO metadata VALUES (?,?)', ('embedding_model', 'test-vector'))
            for key, text, vector in [('variable', '自变量是研究者主动操纵和改变的实验条件。', [1., 0.]),
                    ('measure', '因变量是研究者观察和测量的实验结果。', [0., 1.])]:
                db.execute('INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                    (key, '教材.docx', '实验变量', text, 'text', '[]', 1, key, 1, 2, 3, 4))
                db.execute('INSERT INTO vectors VALUES (?,?)', (key, array('f', vector).tobytes()))
        self.env = patch.dict(os.environ, RAG_RERANK_MODEL='', RAG_RETRIEVAL_PROFILE='hybrid', RAG_EMBED_DEVICE='cpu')
        self.env.start()
        self.embedding = Mock()
        self.embedding.embed.side_effect = lambda queries: iter([[1., 0.]])
        self.model = patch.object(local, '_embedder', return_value=self.embedding)
        self.model.start()

    def tearDown(self):
        self.model.stop(); self.env.stop()
        local._stack.cache_clear(); local._load_index.cache_clear(); clear_reranker_cache()
        self.temp.cleanup()

    def search(self, **kwargs):
        return local.retrieve('什么是自变量', index_path=self.path, **kwargs)

    def test_real_hybrid_returns_canonical_source_and_preserves_index(self):
        before = local.index_signature(self.path); trace = {}
        hits = self.search(trace=trace)
        self.assertEqual(hits[0].chunk_id, 'variable')
        self.assertEqual(hits[0].text, '自变量是研究者主动操纵和改变的实验条件。')
        self.assertEqual((hits[0].chapter_id, hits[0].page, hits[0].block_start, hits[0].block_end), (1, 2, 3, 4))
        self.assertEqual(trace['effective_profile'], 'hybrid')
        self.assertEqual(trace['embedding_dimension'], 2)
        self.assertEqual(local.index_signature(self.path), before)
        self.assertEqual(len(trace['candidates']), len(set(trace['candidates'])))

    def test_chinese_bm25_uses_subwords_and_restores_original_node(self):
        nodes = [TextNode(id_='a', text='研究者操纵自变量以观察结果。'), TextNode(id_='b', text='天气晴朗。')]
        retriever = ChineseBM25Retriever.from_defaults(nodes=nodes, similarity_top_k=2)
        result = retriever.retrieve('自变量')
        self.assertEqual(result[0].node.node_id, 'a')
        self.assertEqual(result[0].node.hash, nodes[0].hash)
        self.assertEqual(result[0].node.text, nodes[0].text)
        self.assertEqual(retriever.retrieve('火星轨道'), [])

    def test_missing_bm25_reports_vector_fallback(self):
        with patch('knowledge.local_rag.retrievers._import_bm25_retriever', return_value=None):
            trace = {}; self.search(trace=trace)
        self.assertEqual(trace['configured_profile'], 'hybrid')
        self.assertEqual(trace['effective_profile'], 'vector')

    def test_query_dimension_mismatch_is_rejected(self):
        self.embedding.embed.side_effect = lambda queries: iter([[1., 0., 0.]])
        with self.assertRaisesRegex(ValueError, '查询'): self.search()

    def test_incomplete_vector_corpus_is_rejected(self):
        with self.database() as db: db.execute("DELETE FROM vectors WHERE id='variable'")
        with self.assertRaisesRegex(ValueError, '完整对应'): self.search()

    def test_nonfinite_corpus_vector_is_rejected(self):
        with self.database() as db:
            db.execute('UPDATE vectors SET data=? WHERE id=?', (array('f', [float('nan'), 0.]).tobytes(), 'variable'))
        with self.assertRaisesRegex(ValueError, '向量'): self.search()

    def test_changed_index_is_loaded_with_new_identity(self):
        first = {}; self.search(trace=first)
        with self.database() as db: db.execute("UPDATE chunks SET text='新的自变量定义。' WHERE id='variable'")
        second = {}; hits = self.search(trace=second)
        self.assertNotEqual(first['index_sha256'], second['index_sha256'])
        self.assertEqual(hits[0].text, '新的自变量定义。')

    def test_wal_file_prevents_mixed_snapshot(self):
        Path(str(self.path) + '-wal').write_bytes(b'pending')
        with self.assertRaisesRegex(ValueError, '正在写入'): self.search()

    def test_low_similarity_is_not_promoted_by_rrf(self):
        self.embedding.embed.side_effect = lambda queries: iter([[-1., -1.]])
        self.assertEqual(self.search(), [])

    def test_index_change_during_query_rejects_results(self):
        def change(queries):
            with self.database() as db: db.execute("UPDATE chunks SET text='changed'")
            return iter([[1., 0.]])
        self.embedding.embed.side_effect = change
        with self.assertRaisesRegex(ValueError, '检索期间'): self.search()

    def test_psychology_entry_calls_local_implementation(self):
        from knowledge.psychology_retrieval import retrieve
        with patch.dict(os.environ, RAG_RETRIEVAL_ENGINE='local_llamaindex'), patch.object(local, 'retrieve', return_value=[]) as call:
            # 让入口在后续目录读取处停止，验证已经选择本地模块而未调用旧召回。
            with patch('knowledge.psychology_retrieval.json.loads', side_effect=RuntimeError('stop after retrieval')):
                with self.assertRaisesRegex(RuntimeError, 'stop after retrieval'): retrieve('自变量', [])
        call.assert_called_once()

    def test_projected_table_keeps_cell_text_and_original_block_range(self):
        from knowledge.psychology_retrieval import retrieve
        from knowledge.textbook import TextbookChunk, terms_for
        text = '维度 | 解释\n变量 | 研究条件'
        chunk = TextbookChunk('教材.docx', '测量', text, terms_for(text), kind='table',
            chunk_id='table-1', chapter_id=1, section_id=1, block_start=0, block_end=0)
        document = {'chapter_id': 1, 'blocks': [{'block_index': 0, 'kind': 'table', 'section_id': 1,
            'text': '表格', 'rows': [['维度', '解释'], ['变量', '研究条件']]}]}
        manifest = [{'chapter_id': 1, 'sections': [{'id': 1, 'page': 1}]}]
        (self.path.parent / 'pdf_manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        with patch.dict(os.environ, RAG_RETRIEVAL_ENGINE='local_llamaindex'), \
                patch.object(local, 'retrieve', return_value=[chunk]), \
                patch('knowledge.psychology_retrieval.documents', return_value=[document]), \
                patch('knowledge.psychology_retrieval.PSYCHOLOGY_DIR', self.path.parent):
            result = retrieve('读取表格', [])
        self.assertEqual(result[0].text, text)
        self.assertEqual(result[0].source_spans[0]['block_id'], 0)
        self.assertEqual(result[0].source_spans[0]['block_end'], len('维度 解释\n变量 研究条件'))


class LocalRerankerTests(unittest.TestCase):
    def tearDown(self): clear_reranker_cache()

    def test_real_node_reranking_preserves_source_ids(self):
        nodes = [NodeWithScore(node=TextNode(id_='a', text='第一段')), NodeWithScore(node=TextNode(id_='b', text='第二段'))]
        trace = {}; model = Mock(); model.predict.return_value = [-2., 3.]
        result = rerank_nodes('问题', nodes, top_k=2, model_name='fixture', loader=lambda name: model, trace=trace)
        self.assertEqual([item.node.node_id for item in result], ['b', 'a'])
        self.assertEqual(trace['rerank_status'], 'applied')
        self.assertGreater(result[0].score, .9)

    def test_missing_model_and_invalid_scores_report_fallback(self):
        nodes = [NodeWithScore(node=TextNode(id_='a', text='原文'))]
        def missing(name): raise ImportError('fixture dependency absent')
        trace = {}; self.assertEqual(rerank_nodes('q', nodes, top_k=1, model_name='missing', loader=missing, trace=trace), nodes)
        self.assertEqual(trace['rerank_status'], 'unavailable')
        for scores in ([], [float('nan')], [1., 2.]):
            clear_reranker_cache(); trace = {}; model = Mock(); model.predict.return_value = scores
            self.assertEqual(rerank_nodes('q', nodes, top_k=1, model_name='broken', loader=lambda name: model, trace=trace), nodes)
            self.assertEqual(trace['rerank_status'], 'failed')
