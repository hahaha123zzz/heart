"""以只读教材索引运行迁入的检索器；模型、证据与配置属于本项目。"""
from array import array
from contextlib import closing
from functools import lru_cache
import hashlib
import math
from pathlib import Path
import sqlite3
import time
from threading import RLock

from llama_index.core import VectorStoreIndex
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.retrievers import QueryFusionRetriever
from llama_index.core.schema import QueryBundle, TextNode

from knowledge.hybrid_retrieval import INDEX, _as_chunk, _embedder
from knowledge.inference_runtime import configured_device
from .config import retrieval_config_from_settings
from .rerank import rerank_nodes
from .retrievers import build_retriever

_LOAD_LOCK = RLock()


class StoredEmbedding(BaseEmbedding):
    def _get_query_embedding(self, query):
        raise RuntimeError('本地检索必须显式提供同模型查询向量')
    async def _aget_query_embedding(self, query):
        return self._get_query_embedding(query)
    def _get_text_embedding(self, text):
        raise RuntimeError('现有教材向量不可被隐式重新生成')


def index_signature(path):
    if Path(str(path) + '-wal').exists(): raise ValueError('教材索引正在写入，拒绝混用版本')
    from knowledge.fixed_book import digest
    return digest(path)


@lru_cache(maxsize=2)
def _load_index(path, signature):
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')
        model = db.execute("SELECT value FROM metadata WHERE key='embedding_model'").fetchone()
        if not model or not model[0]: raise ValueError('教材索引没有嵌入模型身份')
        rows = {row['id']: dict(row) for row in db.execute('SELECT * FROM chunks')}
        vectors = {}
        for row in db.execute('SELECT id,data FROM vectors'):
            values = array('f'); values.frombytes(row['data'])
            vector = list(values)
            if not vector or not all(math.isfinite(value) for value in vector) or not any(vector):
                raise ValueError('教材向量为空、非有限数或零向量')
            vectors[row['id']] = vector
    if not rows or set(vectors) != set(rows): raise ValueError('教材片段与向量未完整对应')
    dimensions = {len(vector) for vector in vectors.values()}
    if len(dimensions) != 1: raise ValueError('教材向量维度不一致')
    if index_signature(path) != signature: raise ValueError('读取期间教材索引发生变化')
    nodes = [TextNode(id_=key, text=row['text'], embedding=vectors[key], metadata={
        'chunk_id': key, 'chapter_id': row['chapter_id'], 'section_id': row['section_id'],
        'section': row['section'], 'page': row['page'], 'source': row['source']}) for key, row in rows.items()]
    index = VectorStoreIndex(nodes, embed_model=StoredEmbedding(model_name=model[0]), show_progress=False)
    return index, rows, vectors, model[0], dimensions.pop()


@lru_cache(maxsize=4)
def _stack(path, signature, config, candidate_top_k):
    index, rows, vectors, model, dimension = _load_index(path, signature)
    storage = Path(__file__).resolve().parents[2] / '.runtime/local-rag' / signature
    retriever = build_retriever(index, storage, top_k=candidate_top_k, config=config)
    return retriever, rows, vectors, model, dimension


def warm():
    import os
    os.environ.setdefault('RAG_RERANK_MODEL', 'BAAI/bge-reranker-base')
    config = retrieval_config_from_settings()
    _stack(str(INDEX.resolve()), index_signature(INDEX), config, config.rerank_candidate_top_k(6))


def retrieve(query, *, limit=6, preferred_types=(), index_path=None, trace=None, chapter_id=None, section_id=None):
    if not isinstance(query, str) or len(query) > 4000: raise ValueError('检索问题无效或过长')
    if not 1 <= limit <= 40: raise ValueError('检索结果数量必须为1到40')
    if not query.strip(): return []
    config = retrieval_config_from_settings()
    path = str(Path(index_path or INDEX).resolve())
    signature = index_signature(path)
    with _LOAD_LOCK:
        stack = _stack(path, signature, config, config.rerank_candidate_top_k(limit))
    retriever, rows, vectors, model, dimension = stack
    status = trace if trace is not None else {}
    status.update(engine='local_llamaindex', index_sha256=signature, embedding_model=model,
        embedding_dimension=dimension, corpus_size=len(rows), configured_profile=config.profile,
        effective_profile='hybrid' if isinstance(retriever, QueryFusionRetriever) else 'vector',
        embedding_device=configured_device('EMBED'), rerank_status='disabled')
    started = time.monotonic()
    vector = list(next(iter(_embedder(model).embed([query]))))
    status.update(embedding_batches=1, embedding_texts=1, embedding_seconds=time.monotonic()-started)
    if len(vector) != dimension or not all(math.isfinite(float(value)) for value in vector) or not any(vector):
        raise ValueError('查询与教材向量维度/数值不一致')
    norm = math.sqrt(sum(float(value) ** 2 for value in vector))
    started = time.monotonic()
    candidates = retriever.retrieve(QueryBundle(query_str=query, embedding=vector))
    unique = {}
    for node in candidates: unique.setdefault(node.node.node_id, node)
    candidates = list(unique.values())
    if chapter_id is not None:
        # 局部向量候选独立召回，不能等全书 Top-K 后再过滤当前小节。
        import numpy as np
        for section in dict.fromkeys((section_id, None)):
            keys = [key for key, row in rows.items() if row['chapter_id'] == chapter_id
                    and (section is None or row['section_id'] == section)]
            if keys:
                matrix = np.asarray([vectors[key] for key in keys], dtype=np.float32)
                scores = (matrix @ np.asarray(vector, dtype=np.float32)) / np.linalg.norm(matrix, axis=1)
                for position in np.argsort(scores)[-8:][::-1]:
                    key = keys[int(position)]
                    if key not in unique:
                        from llama_index.core.schema import NodeWithScore
                        node = NodeWithScore(node=_load_index(path, signature)[0].docstore.docs[key], score=float(scores[position]))
                        unique[key] = node;candidates.append(node)
    if any(node.node.node_id not in rows for node in candidates): raise ValueError('检索返回非当前教材节点')
    dense = {node.node.node_id: sum(float(a) * b for a, b in zip(vector, vectors[node.node.node_id])) /
        (norm * math.sqrt(sum(value * value for value in vectors[node.node.node_id]))) for node in candidates}
    status['candidates'] = [node.node.node_id for node in candidates]
    status['recall_seconds'] = time.monotonic()-started
    if config.reranker_model:
        started = time.monotonic()
        candidates = rerank_nodes(query, candidates, top_k=len(candidates) or 1,
            model_name=config.reranker_model, trace=status)
        status['rerank_seconds'] = time.monotonic()-started
    if status['rerank_status'] == 'applied':
        import os
        minimum = float(os.getenv('RAG_RERANK_MIN_PROBABILITY', '0.15'))
        if not 0 < minimum < 1: raise ValueError('重排相关性门槛必须在0和1之间')
        candidates = [node for node in candidates if node.score is not None and node.score >= minimum]
    else:
        # RRF只有排序意义，不能当相似度；重排不可用时保留已有余弦证据门槛。
        candidates = [node for node in candidates if dense[node.node.node_id] >= .58]
    if preferred_types:
        candidates.sort(key=lambda node: rows[node.node.node_id]['kind'] not in preferred_types)
    if chapter_id is not None:
        candidates.sort(key=lambda node: float(node.score or 0) +
            (.025 if rows[node.node.node_id]['chapter_id'] == chapter_id else 0) +
            (.015 if rows[node.node.node_id]['chapter_id'] == chapter_id and
             rows[node.node.node_id]['section_id'] == section_id else 0), reverse=True)
    selected = candidates[:limit]
    status['rerank_scores'] = {node.node.node_id: float(node.score) for node in candidates if node.score is not None}
    if index_signature(path) != signature: raise ValueError('检索期间教材索引已变化')
    status['selected'] = [node.node.node_id for node in selected]
    status['dense_scores'] = dense
    return [_as_chunk(rows[node.node.node_id]) for node in selected]
