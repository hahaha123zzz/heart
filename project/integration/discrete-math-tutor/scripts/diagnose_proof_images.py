"""诊断图示证明审核格式，保留最终JSON，不保存隐藏推理。"""
import json,time
from pathlib import Path
from llm.client import LLMClient
from agents.proof_checker import ProofChecker,SYSTEM_PROMPT,AuditPayload,CHECKS
from knowledge.proof_units import units_for,focus_pages
from knowledge.pdf_reader import PDFSelection,resolve_selection
BASE=Path(__file__).resolve().parents[1]
old=json.loads((BASE/'artifacts/long-proofs-quality-gate-gpu.json').read_text(encoding='utf8'))
case=next(c for c in old if c['case']['id']=='five-color-step')
u=units_for(8)['定理8.11']; pages=focus_pages(u,case['case']['question'])
resolved=resolve_selection(PDFSelection(document_id=u.record['document_id'],version=u.record['version'],kind='text',rects=[r for r in u.rects if r['page'] in pages]))
client=LLMClient(mock=False);result={}
start=time.perf_counter()
try:
 data=client.chat_json([{'role':'system','content':SYSTEM_PROMPT},{'role':'user','content':json.dumps({'question':case['case']['question'],'response':case['response']['reply'],'textbook_excerpts':u.text},ensure_ascii=False)}],temperature=0,max_tokens=12000,retries=0,timeout=60,reasoning_effort='low',image_paths=resolved['images'])
 result['data']=data
 try:
  payload=AuditPayload.model_validate(data)
  result['invalid_quotes']=[c.quote for c in payload.checks if c.quote and c.quote not in case['response']['reply']]
 except Exception as e: result['schema_error']=str(e)
except Exception as e:result['error_type']=type(e).__name__;result['error']=str(e)
result['seconds']=time.perf_counter()-start
(BASE/'artifacts/proof-audit-image-diagnostic.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(result,ensure_ascii=False),flush=True)
