"""仅面向显式指定的隔离本机服务；不启动/切换正式服务。"""
import argparse
import json
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4
import httpx


def check(base_url):
    url = urlsplit(base_url)
    if url.hostname not in ('127.0.0.1','localhost') or url.scheme != 'http' or url.port in (None,8000):
        raise ValueError('请使用显式端口的隔离本机服务，禁止默认正式端口8000')
    run=uuid4().hex[:12]
    owner={'student_id':'layer5-'+run,'session_id':'layer5-'+run}
    report={'run':run,'passed':False,'cases':[]}
    with httpx.Client(base_url=base_url,trust_env=False,timeout=180) as client:
        client.post('/api/accounts/test',json={'student_id':owner['student_id']}).raise_for_status()
        for i, message in enumerate(('我想学习教材第一章的内容，直接讲解，不出题',
                '自变量和因变量有什么区别？请按教材说明，不出题',
                '请换一个生活化的例子解释这两个变量，不出题')):
            request={**owner,'request_id':run+'-'+str(i),'message':message,
                     'reader_location':{'chapter_id':2,'section_id':2}}
            start=time.monotonic();response=client.post('/api/chat',json=request)
            response.raise_for_status();data=response.json()
            item={'message':message,'seconds':round(time.monotonic()-start,3),'response':data}
            report['cases'].append(item)
            if data.get('answer_status')!='answered' or not data.get('learning_response'):
                report['error']='missing_composed_answer';return report
            content=data['learning_response']
            assert content['reply']==data['reply']
            assert content['blocks'] and all(b['status']=='published' for b in content['blocks'])
            assert data.get('pdf_references'), 'missing_verified_citations'
            assert '"claims"' not in data['reply'] and 'DSML' not in data['reply']
            replay=client.post('/api/chat',json=request).json()
            assert replay['learning_response']==content and replay['conversation_id']==data['conversation_id']
        history=client.get('/api/students/'+owner['student_id']+'/conversation',params={'session_id':owner['session_id']}).json()
        for item in report['cases']:
            data=item['response']
            saved=next(row for row in history if row.get('id')==data['conversation_id'])
            assert saved['selection_ref']['learning_response']==data['learning_response']
    report['owner']=owner
    report['passed']=True
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=check(args.base_url)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'cases':len(report['cases']),'output':str(args.output)},ensure_ascii=False))
    raise SystemExit(0 if report['passed'] else 1)
