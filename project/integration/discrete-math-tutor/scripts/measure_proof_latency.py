"""流式阶段计时；原始回答保留，验收标准在执行前冻结。"""
import argparse,json,time,uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import requests
BASE=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--label',required=True);p.add_argument('--ids',default='');p.add_argument('--cases',default='tests/data/proof_latency_holdout_2026_10_11.json');p.add_argument('--include-history',action='store_true');args=p.parse_args()
URL='http://127.0.0.1:8000'
for _ in range(120):
 try:
  if requests.get(URL+'/health',timeout=2).ok:break
 except requests.RequestException:pass
 time.sleep(2)
else:raise RuntimeError('服务未就绪')
cases=json.loads((BASE/args.cases).read_text(encoding='utf8'))['cases']
if args.ids:cases=[c for c in cases if c['id'] in args.ids.split(',')]
def run(case):
 sid='proof-latency-test-'+uuid.uuid4().hex[:10];start=time.perf_counter();events=[];result={};status=None
 try:
  with requests.post(URL+'/api/chat/stream',json={'student_id':sid,'account_type':'test','message':case['question']},stream=True,timeout=(10,180)) as r:
   status=r.status_code;r.raise_for_status();event=''
   for line in r.iter_lines(chunk_size=1):
    line=line.decode('utf8')
    if line.startswith('event: '):event=line[7:]
    elif line.startswith('data: '):
     data=json.loads(line[6:]);elapsed=round(time.perf_counter()-start,3)
     if event=='progress':events.append({'seconds':elapsed,**data})
     elif event in ('done','error'):result=data;break
  durations={}
  for e in events:
   if e['status']=='running':durations.setdefault(e['stage'],{'start':e['seconds']})
   elif e['status']=='completed' and e['stage'] in durations:durations[e['stage']]['seconds']=round(e['seconds']-durations[e['stage']]['start'],3)
  out={'case':case,'http':status,'seconds':round(time.perf_counter()-start,3),'stages':durations,'events':events,'response':result}
  if args.include_history:
   h=requests.get(URL+'/api/students/'+sid+'/conversation',timeout=15)
   out['history_http']=h.status_code;out['history']=h.json() if h.ok else []
  print(case['id'],out['seconds'],result.get('answer_status'),result.get('quality'),flush=True)
  return out
 finally:
  cleanup=requests.delete(URL+'/api/accounts/test/'+sid,timeout=15);print('cleanup',sid,cleanup.status_code,flush=True)
with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,cases))
(BASE/('artifacts/proof-latency-'+args.label+'.json')).write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
