"""只读取检索结果，诊断定义补检索，不创建或修改学习账户。"""
import json
from pathlib import Path
from llm.client import LLMClient
from knowledge.hybrid_retrieval import retrieve_hybrid
from knowledge.textbook import load_textbook
queries=['欧拉回路的定义','欧拉回路的定义；无向图存在欧拉回路的充要条件（连通且所有顶点度数为偶数）；定理7.1与欧拉回路存在性之间的逻辑关联']
results=[]
for query in queries:
    chunks=retrieve_hybrid(query,load_textbook(),limit=3)
    results.append({'query':query,'sources':[{'id':c.chunk_id,'section':c.section,'text':c.text} for c in chunks]})
Path('artifacts/evidence-recovery-retrieval.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
print('diagnosis complete')
