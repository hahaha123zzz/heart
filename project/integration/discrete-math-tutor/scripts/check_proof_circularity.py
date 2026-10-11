"""核验已发现的循环论证，不把模型通过当作数学正确性保证。"""
import json,sqlite3
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(override=True)
from llm.client import LLMClient
from agents.quality_checker import QualityChecker
from agents.teaching_planner import TeachingPlan
from models.student_state import StudentState
from knowledge.hybrid_retrieval import _as_chunk
from knowledge.pdf_evidence import enrich_sources
from knowledge.textbook import format_excerpts
BASE=Path(__file__).resolve().parents[1]
previous=json.loads((BASE/'artifacts/tables-proofs-upgraded-first.json').read_text(encoding='utf8'))
item=next(x for x in previous if x['case']['id']=='tree-proof')
c=sqlite3.connect(BASE/'knowledge/rag_index_v2.sqlite3');c.row_factory=sqlite3.Row
source=_as_chunk(c.execute('SELECT * FROM chunks WHERE id=?',('ch8-b488-0',)).fetchone())
hits,sup=enrich_sources([source],item['case']['question'])
r=item['response']
check=QualityChecker(LLMClient(mock=False)).check(r['reply'].replace('[2]','[1]'),StudentState(**r['student_state']),TeachingPlan(**r['teaching_plan']),item['case']['question'],textbook_excerpts=format_excerpts(hits),figure_images=sup.images)
out={'case':'known_circular_proof','quality':check.model_dump(),'response':r['reply']}
(BASE/'artifacts/tables-proofs-circular-check.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(out,ensure_ascii=False),flush=True)