import json,time,uuid,sys
from pathlib import Path
import requests
BASE=Path(__file__).resolve().parents[1]
url='http://127.0.0.1:8000'
for attempt in range(80):
    try:
        if requests.get(url+'/health',timeout=2).status_code==200: break
    except requests.RequestException: pass
    time.sleep(1)
else: raise RuntimeError('服务未启动')
results=[]
cases=[('ordered-pair','教材的 ordered pairs 为什么不能直接当成二元素集合？',True),
       ('components','定义笛卡尔积时为何要区分第一和第二分量？',True),
       ('subset-proof','已知 A⊆B 且 B⊆C，为什么 A⊆C？请结合教材解释。',True),
       ('sql','怎样在订单数据库建立 ordered pairs 索引？',False),
       ('js','p→q 在 JavaScript 程序的异步任务调度中如何实现？',False)]
for tag,message,expected in cases:
    if '--proof-only' in sys.argv and tag != 'subset-proof': continue
    sid='pdf-evidence-smoke-'+uuid.uuid4().hex[:10]
    start=time.perf_counter()
    try:
        response=requests.post(url+'/api/chat',json={'student_id':sid,'account_type':'test','message':message},timeout=180)
        body=response.json()
        result={'tag':tag,'question':message,'expected_allowed':expected,'http_status':response.status_code,
                'elapsed_seconds':round(time.perf_counter()-start,2),'response':body}
        result['crop_statuses']=[requests.get(url+ref['image_url'],timeout=15).status_code for ref in body.get('pdf_image_refs',[])]
        results.append(result)
        print(json.dumps(result,ensure_ascii=False),flush=True)
    finally:
        cleanup=requests.delete(url+'/api/accounts/test/'+sid,timeout=15)
        print('cleanup',sid,cleanup.status_code,flush=True)
        (BASE/('artifacts/pdf-evidence-proof-clean.json' if '--proof-only' in sys.argv else 'artifacts/pdf-evidence-real-api.json')).write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
