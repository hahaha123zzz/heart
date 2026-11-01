"""仅面向显式指定的隔离本机服务；不启动/切换正式服务。"""
import argparse
import json
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4
import httpx


def check(base_url, batch='c1'):
    url = urlsplit(base_url)
    if url.hostname not in ('127.0.0.1','localhost') or url.scheme != 'http' or url.port in (None,8000):
        raise ValueError('请使用显式端口的隔离本机服务，禁止默认正式端口8000')
    run=uuid4().hex[:12]
    owner={'student_id':'layer5-'+run,'session_id':'layer5-'+run}
    report={'run':run,'passed':False,'cases':[]}
    with httpx.Client(base_url=base_url,trust_env=False,timeout=180) as client:
        client.post('/api/accounts/test',json={'student_id':owner['student_id']}).raise_for_status()
        messages = ('我想学习教材第一章的内容，直接讲解，不出题',
                '自变量和因变量有什么区别？请按教材说明，不出题',
                '请换一个生活化的例子解释这两个变量，不出题') if batch == 'c1' else (
                '请按教材解释自变量和因变量的区别，并用对比卡展示，不出题',
                '现在练习，针对自变量出一道理解检查题',
                '回到刚才的题',
                '只给这道题一点提示，不要完整答案',
                '先解释什么是操作性定义，再回到刚才的题，不要替我作答')
        for i, message in enumerate(messages):
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
            if batch == 'c1':
                assert data.get('pdf_references'), 'missing_verified_citations'
            else:
                assert all(b['content_origin']=='host_snapshot' for b in content['blocks'])
                if i == 0:
                    assert any(card['kind']=='concept_comparison' for card in data.get('learning_cards',[]))
                if i in (1,2,3,4):
                    assert data.get('teaching',{}).get('pending_check'), 'pending_question_missing'
                if i == 2:
                    prior=report['cases'][1]['response']['teaching']['pending_check']
                    assert data['publication_mode']=='saved_formative_question'
                    assert prior==data['teaching']['pending_check'], 'pending_question_changed'
                if i in (3,4):
                    assert data['teaching']['pending_check']==report['cases'][1]['response']['teaching']['pending_check']
                if i == 4 and data.get('input_understanding'):
                    assert data.get('input_resume_question_id')==data['teaching']['pending_check']['question_id']
                    assert data['reply'].rstrip().endswith(data['teaching']['pending_check']['prompt'].rstrip())
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
    parser.add_argument('--batch',choices=('c1','c2'),default='c1')
    args=parser.parse_args()
    report=check(args.base_url,args.batch)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'cases':len(report['cases']),'output':str(args.output)},ensure_ascii=False))
    raise SystemExit(0 if report['passed'] else 1)
