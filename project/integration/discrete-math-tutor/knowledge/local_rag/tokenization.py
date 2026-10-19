"""BM25沿用项目中文词项；融合时恢复原节点，保持与向量路相同的hash。"""
from llama_index.core.schema import NodeWithScore, QueryBundle
from llama_index.retrievers.bm25 import BM25Retriever
from knowledge.textbook import terms_for


class ChineseBM25Retriever(BM25Retriever):
    @classmethod
    def from_defaults(cls, *, index=None, nodes=None, **kwargs):
        original = nodes if nodes is not None else list(index.docstore.docs.values())
        tokenized = [node.model_copy(update={'text': ' '.join(sorted(terms_for(node.text))),
            'metadata': {}}) for node in original]
        retriever = super().from_defaults(nodes=tokenized, language=None, skip_stemming=True, **kwargs)
        retriever.original_nodes = {node.node_id: node for node in original}
        return retriever

    def _retrieve(self, query_bundle):
        terms = terms_for(query_bundle.query_str)
        if not terms: return []
        results = super()._retrieve(QueryBundle(' '.join(sorted(terms))))
        return [NodeWithScore(node=self.original_nodes[result.node.node_id], score=result.score)
            for result in results if result.score is not None and result.score > 0]
