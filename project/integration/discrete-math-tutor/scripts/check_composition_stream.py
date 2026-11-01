"""隔离HTTP验收：核验块早于最终保存，正文/编号不回退，重复请求不重复生成。"""
import argparse
import json
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4
import httpx


def run(base_url, output, payload=None, on_first=None):
    parsed=urlsplit(base_url)
    if parsed.hostname not in ('127.0.0.1','localhost') or parsed.port in (None,8000):
        raise ValueError('仅允许显式隔离本机端口')
    owner='c3-'+uuid4().hex[:12]
    payload=payload or {'student_id':owner,'session_id':owner,'request_id':uuid4().hex,
        'message':'我不懂自变量，请举一个生活例子，不出题',
        'reader_location':{'chapter_id':2,'section_id':2}}
    report={'passed':False,'payload':payload,'blocks':[],'events':[]}
    started=time.monotonic()
    try:
        with httpx.Client(base_url=base_url,trust_env=False,timeout=180) as client:
            client.post('/api/accounts/test',json={'student_id':payload['student_id']}).raise_for_status()
            with client.stream('POST','/api/chat/stream',json=payload) as stream:
                stream.raise_for_status();event=''
                for line in stream.iter_lines():
                    if line.startswith('event:'):event=line[6:].strip()
                    if not line.startswith('data:'):continue
                    data=json.loads(line[5:])
                    elapsed=round(time.monotonic()-started,3)
                    report['events'].append({'event':event,'seconds':elapsed})
                    if event=='answer_blocks':
                        p=data['publication']
                        if report['blocks']:assert p['reply'].startswith(report['blocks'][-1]['publication']['reply'])
                        report['blocks'].append({'seconds':elapsed,'publication':p,'identity':{
                            k:data[k] for k in ('task_id','task_revision','answer_id','seq')}})
                        output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
                        if on_first and len(report['blocks'])==1:on_first(report)
                    if event=='done':report['result']=data
            result=report.get('result') or {}
            assert result.get('answer_status')=='answered', result.get('reply')
            assert len(report['blocks'])>=2,'missing_incremental_blocks'
            assert report['events'][-1]['seconds']>=report['blocks'][0]['seconds']
            assert report['blocks'][-1]['publication']['reply'] in result['reply']
            replay=client.post('/api/chat',json=payload).json()
            assert replay['conversation_id']==result['conversation_id']
            assert replay['learning_response']==result['learning_response']
            report['passed']=True
    except Exception as exc:
        report['error']=type(exc).__name__+': '+str(exc)[:1000]
    finally:
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.parent.mkdir(parents=True,exist_ok=True)
    result=run(args.base_url,args.output)
    print(json.dumps({'passed':result['passed'],'blocks':len(result['blocks']),'error':result.get('error')},ensure_ascii=False))
    raise SystemExit(not result['passed'])
