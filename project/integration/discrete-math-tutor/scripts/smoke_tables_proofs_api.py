"""冻结问题的实际问答诊断；结果人工核对，自动质检通过不等于答案正确。"""
import json,time,uuid,argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import requests
BASE=Path(__file__).resolve().parents[1]
URL='http://127.0.0.1:8000'
p=argparse.ArgumentParser(); p.add_argument('--label',required=True); p.add_argument('--ids',default=''); p.add_argument('--url',default=URL); args=p.parse_args(); URL=args.url
for attempt in range(180):
 try:
  if requests.get(URL+'/health',timeout=2).status_code==200: break
 except requests.RequestException: pass
 time.sleep(2)
else: raise RuntimeError('服务预热未完成，请检查启动日志')
cases=json.loads((BASE/'tests/data/rag_tables_proofs_2026_10_11.json').read_text(encoding='utf8'))['cases']
if args.ids: cases=[c for c in cases if c['id'] in args.ids.split(',')]
def run(case):
 sid='tables-proofs-test-'+uuid.uuid4().hex[:10]; start=time.perf_counter()
 try:
  r=requests.post(URL+'/api/chat',json={'student_id':sid,'account_type':'test','message':case['question']},timeout=180)
  body=r.json(); crops=[requests.get(URL+x['image_url'],timeout=15).status_code for x in body.get('pdf_image_refs',[])]
  out={'case':case,'http':r.status_code,'seconds':round(time.perf_counter()-start,2),'crop_statuses':crops,'response':body}
  print(case['id'],r.status_code,body.get('evidence_check'),body.get('pdf_evidence'),body.get('textbook_sources'),body.get('reply'),flush=True)
  return out
 finally:
  cleanup=requests.delete(URL+'/api/accounts/test/'+sid,timeout=15); print('cleanup',sid,cleanup.status_code,flush=True)
with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(run,cases))
(BASE/f'artifacts/tables-proofs-{args.label}.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
