import json,sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(override=True)
from llm.client import LLMClient
from agents.context_sufficiency import ContextSufficiency
from knowledge.hybrid_retrieval import _as_chunk
from knowledge.pdf_evidence import enrich_sources
BASE=Path(__file__).resolve().parents[1]
db=sqlite3.connect(BASE/'knowledge/rag_index_v2.sqlite3');db.row_factory=sqlite3.Row
chunk=_as_chunk(db.execute("select * from chunks where id='ch1-b317-0'").fetchone());db.close()
sources,pdf=enrich_sources([chunk])
questions=[('ordered-pair','教材的 ordered pairs 为什么不能直接当成二元素集合？',True),
('components','定义笛卡尔积时为何要区分第一和第二分量？',True),
('sql','怎样在订单数据库建立 ordered pairs 索引？',False),
('js','p→q 在 JavaScript 程序的异步任务调度中如何实现？',False)]
def run(case):
    tag,question,expected=case
    decision=ContextSufficiency(LLMClient(mock=False)).check(question,
        [{'id':'1','source':s.source,'section':s.section,'text':s.text} for s in sources],image_paths=pdf.images)
    result={'id':tag,'question':question,'expected_allowed':expected,'correct':decision.allowed==expected and decision.status!='unavailable',
            'decision':decision.model_dump(),'pdf_evidence':pdf.public()}
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return result
with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(run,questions))
(BASE/'artifacts/pdf-evidence-judge.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
