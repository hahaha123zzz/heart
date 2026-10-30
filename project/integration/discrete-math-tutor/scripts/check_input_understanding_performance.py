"""隔离 HTTP 测量；逐次保存结果，模型失败不会作为成功样本。"""
import argparse
import json
from pathlib import Path
import sqlite3
import time
import urllib.request
from uuid import uuid4


PAIRS = [
    ('自变量','因变量'),('内部效度','外部效度'),('被试内设计','被试间设计'),
    ('相关','因果'),('主效应','交互作用'),('信度','效度'),
]
TEMPLATES = [
    '先解释{a}，再比较{a}与{b}，最后总结，不要出题。',
    '先说明{a}，然后比较{b}，最后概括关键差异，不要出题。',
    '先讲解{a}，再联系{b}，最后说说两者如何区分，不要出题。',
    '先介绍{a}，再解释{b}，最后进行比较，不要出题。',
    '先解释{a}，再说{b}，最后用简短文字总结区别，不要出题。',
]
SIMPLE = ['什么是自变量？','什么是因变量？','请解释内部效度。','什么是外部效度？',
          '请解释信度。','什么是操作性定义？','主效应是什么？','什么是交互作用？',
          '随机分配是什么？','请解释反应时。']
MATRIX = [
    '先解释自变量，再比较自变量与因变量，最后总结，不要出题。',
    '先说明内部效度，然后比较外部效度，最后概括关键差异，不要出题。',
    '如果教材提到随机分配，先解释随机分配，否则说明依据不足，再介绍随机区组设计。',
    '一方面解释被试内设计，另一方面比较被试间设计，不要出题。',
    '先解释第一章的实验研究程序，再比较第二章的变量控制，最后总结二者关系，不要出题。',
    '以后详细一点，但这次先解释自变量，再比较因变量，最后简短总结，不要出题。',
    '先解释自变量，再比较额外变量，最后总结，不要给完整答案，也不要出题。',
    '先介绍主效应，再解释交互作用，最后进行比较，不要出题。',
]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',required=True)
    parser.add_argument('--database',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--suite',choices=('complex','paired','matrix'),required=True)
    args=parser.parse_args()
    messages=([template.format(a=a,b=b) for a,b in PAIRS for template in TEMPLATES]
              if args.suite=='complex' else MATRIX if args.suite=='matrix' else SIMPLE)
    rows=[]
    args.output.parent.mkdir(parents=True,exist_ok=True)
    for index,message in enumerate(messages,1):
        payload=dict(student_id='input-perf-'+uuid4().hex[:12],session_id='independent',
                     account_type='test',request_id=uuid4().hex,message=message,
                     reader_location=dict(chapter_id=2,section_id=2))
        row=dict(index=index,payload=payload);rows.append(row)
        start=time.perf_counter();first=None;event='';data=[];result=None
        try:
            req=urllib.request.Request(args.base_url.rstrip('/')+'/api/chat/stream',
                data=json.dumps(payload).encode('utf8'),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=180) as response:
                for raw in response:
                    line=raw.decode('utf8').rstrip('\r\n')
                    if line.startswith('event: '):event=line[7:]
                    elif line.startswith('data: '):data.append(line[6:])
                    elif not line:
                        if event=='answer_delta' and first is None and data:
                            value=json.loads('\n'.join(data))
                            if value.get('role')=='answer' and value.get('text'):first=time.perf_counter()-start
                        if event=='done' and data:result=json.loads('\n'.join(data))
                        event='';data=[]
            row['result']=result
            if result and result.get('task_id'):
                with sqlite3.connect(args.database.resolve().as_uri()+'?mode=ro',uri=True) as db:
                    found=db.execute('SELECT context FROM learning_tasks WHERE id=?',(result['task_id'],)).fetchone()
                    if found:row['understanding']=json.loads(found[0]).get('input_understanding')
        except Exception as exc:
            row['error']=type(exc).__name__+': '+str(exc)
        row.update(seconds=round(time.perf_counter()-start,4),first_token_seconds=round(first,4) if first is not None else None)
        args.output.write_text(json.dumps(dict(suite=args.suite,rows=rows),ensure_ascii=False,indent=2),encoding='utf8')
        print(json.dumps(dict(index=index,status=(result or {}).get('answer_status'),
                              parser=(row.get('understanding') or {}).get('parser'),seconds=row['seconds'],
                              first_token_seconds=row['first_token_seconds'],error=row.get('error')),ensure_ascii=False),flush=True)


if __name__=='__main__':main()
