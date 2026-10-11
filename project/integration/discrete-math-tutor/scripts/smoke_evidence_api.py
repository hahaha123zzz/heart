import json,time,uuid,sys
from pathlib import Path
import requests
BASE=Path(__file__).resolve().parents[1]
url='http://127.0.0.1:8000'
results=[]
for tag,message in [('outside-js','p→q 在 JavaScript 程序的异步任务调度中如何实现？'),('outside-db','怎样在订单数据库建立 ordered pairs 索引？'),('inside','命题 A∧B 在什么情况下为真？请结合教材解释。')]:
    if '--inside-only' in sys.argv and tag != 'inside': continue
    sid='evidence-smoke-'+uuid.uuid4().hex[:12]
    start=time.perf_counter()
    try:
        response=requests.post(url+'/api/chat',json={'student_id':sid,'account_type':'test','message':message},timeout=180)
        result={'tag':tag,'question':message,'http_status':response.status_code,'elapsed_seconds':round(time.perf_counter()-start,2),'response':response.json()}
        results.append(result)
        print(json.dumps(result,ensure_ascii=False),flush=True)
    finally:
        cleanup=requests.delete(url+'/api/accounts/test/'+sid,timeout=15)
        print('cleanup',sid,cleanup.status_code,flush=True)
(BASE/('artifacts/evidence-real-api-inside.json' if '--inside-only' in sys.argv else 'artifacts/evidence-real-api.json')).write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
