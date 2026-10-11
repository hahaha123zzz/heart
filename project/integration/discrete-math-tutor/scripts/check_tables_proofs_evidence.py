"""不经过 GPU 召回的受控诊断；验证原页补充后是否足以回答两项基线失败。"""
import json,sqlite3
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(override=True)
from llm.client import LLMClient
from agents.context_sufficiency import ContextSufficiency
from knowledge.hybrid_retrieval import _as_chunk
from knowledge.pdf_evidence import enrich_sources
BASE=Path(__file__).resolve().parents[1]
cases=json.loads((BASE/'tests/data/rag_tables_proofs_2026_10_11.json').read_text(encoding='utf8'))['cases']
c=sqlite3.connect(BASE/'knowledge/rag_index_v2.sqlite3');c.row_factory=sqlite3.Row
results=[]
for tag,key in [('relation-table','multimodal_chunks.jsonl-884'),('tree-proof','ch8-b488-0')]:
 case=next(x for x in cases if x['id']==tag)
 source=_as_chunk(c.execute('SELECT * FROM chunks WHERE id=?',(key,)).fetchone())
 hits,sup=enrich_sources([source],case['question'])
 decision=ContextSufficiency(LLMClient(mock=False)).check(case['question'],[{'id':'1','source':hits[0].source,'section':hits[0].section,'text':hits[0].text}],image_paths=sup.images if sup else None)
 result={'id':tag,'decision':decision.model_dump(),'pdf_evidence':sup.public() if sup else None};results.append(result)
 print(json.dumps(result,ensure_ascii=False),flush=True)
(BASE/'artifacts/tables-proofs-controlled.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')