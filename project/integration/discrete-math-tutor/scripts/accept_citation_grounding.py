"""真实完整回答链路的冻结场景验收；独立课程库、逐条保存原始结果。"""
import argparse,hashlib,importlib,json,os,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BENCHMARK=ROOT.parents[1]/'docs/research/2026-10-16-citation-grounding/benchmark.json'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--mode',choices=['legacy','candidate'],required=True);parser.add_argument('--index',type=Path)
    parser.add_argument('--split',choices=['development','holdout','all'],default='all')
    parser.add_argument('--repeat-high-risk',action='store_true');args=parser.parse_args()
    if args.output.exists():raise ValueError('报告已存在，不覆盖')
    if args.mode=='candidate' and not args.index:raise ValueError('新链路必须显式指定独立索引')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    data=json.loads(BENCHMARK.read_text(encoding='utf-8'))
    cases=[c for c in data['cases'] if args.split=='all' or c['split']==args.split]
    if args.repeat_high_risk:cases=[c for c in cases for _ in range(3 if c['high_risk'] else 1)]
    report={'mode':args.mode,'benchmark_sha256':hashlib.sha256(BENCHMARK.read_bytes()).hexdigest(),
        'method':'真实TaskService与生成/质检；合成账户；独立临时数据库；模型核验不等于教师审核',
        'request_policy':'版本负例必须携带实际错误版本选区；其他场景使用冻结问题及阅读位置。早期legacy-100未提交错误版本，仅作探索基线。','results':[]}
    report['code_sha256']={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
        for path in [ROOT/'orchestrator.py',ROOT/'practice_api.py',ROOT/'frontend/app.js',
            *sorted((ROOT/'knowledge').glob('*.py')),*sorted((ROOT/'agents').glob('*.py'))]}
    with tempfile.TemporaryDirectory(prefix='citation-acceptance-') as directory:
        os.environ.update(TUTOR_COURSE='experimental-psychology-3',LLM_MOCK='0',MEMORY_WORKER_ENABLED='0',VISUALIZATION_ON_DEMAND='0',
            COURSE_DATABASE_URL='sqlite:///'+str(Path(directory)/'course.db'),
            CITATION_GROUNDING_MODE='active' if args.mode=='candidate' else 'off')
        if args.index:os.environ['CITATION_GROUNDING_INDEX']=str(args.index.resolve())
        from llm.client import LLMClient
        original=LLMClient.chat;raw_original=LLMClient._one_call;calls=[];raw_calls=[];retrievals=[]
        def raw_measured(client,messages,*positional,**kw):
            started=time.monotonic();call={'agent':str(messages[0].get('content',''))[:60]};raw_calls.append(call)
            try:
                response,finish=raw_original(client,messages,*positional,**kw)
                call.update(response=response,finish_reason=finish);return response,finish
            finally:call['seconds']=round(time.monotonic()-started,3)
        def measured(client,messages,*positional,**kw):
            started=time.monotonic();kw.setdefault('timeout',30)
            call={'agent':str(messages[0].get('content',''))[:60]};calls.append(call)
            try:
                response=original(client,messages,*positional,**kw)
                call['response']=response
                return response
            finally:call['seconds']=round(time.monotonic()-started,3)
        LLMClient.chat=measured;LLMClient._one_call=raw_measured
        try:
            from main import _run_turn,orchestrator
            from models.chat_request import ChatRequest
            from database.database import engine
            assert Path(engine.url.database).resolve().parent==Path(directory).resolve()
            report['mock']=orchestrator.llm.mock;assert not report['mock']
            flow=importlib.import_module('orchestrator');retrieve_original=flow.retrieve_course
            def retrieve_measured(query,*positional,**kw):
                sources=retrieve_original(query,*positional,**kw)
                retrievals.append({'query':query,'sources':[{key:getattr(s,key) for key in ('source','chapter_id','section_id','chunk_id','text','block_start','block_end','source_spans')} for s in sources]})
                return sources
            flow.retrieve_course=retrieve_measured
            for order,case in enumerate(cases,1):
                item=case['support'][0];started=time.monotonic();calls.clear();raw_calls.clear();retrievals.clear();stages=[]
                row={'id':case['id'],'split':case['split'],'category':case['category'],'order':order}
                try:
                    selection=None
                    if case.get('mutation')=='wrong_version':
                        selection={'document_id':item['document_id'],'version':item['version'],'kind':'area',
                            'rects':[{'page':item['pages'][0],'x1':.1,'y1':.1,'x2':.2,'y2':.2}]}
                    result=_run_turn(ChatRequest(student_id=f'citation-{args.mode}-{order}',session_id=f'citation-{order}',request_id=f'citation-{order}',
                        message=case['question'],selection=selection,reader_location={'chapter_id':item['chapter'],'section_id':item['section_id']}),
                        progress=lambda stage,label,detail='':stages.append({'stage':stage,'label':label,'seconds':round(time.monotonic()-started,3)}))
                    row['result']=result
                except Exception as exc:row['error']={'type':type(exc).__name__,'message':str(exc)[:500]}
                row.update(seconds=round(time.monotonic()-started,3),calls=list(calls),raw_calls=list(raw_calls),retrievals=list(retrievals),stages=stages)
                report['results'].append(row);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
                print(order,case['id'],row.get('result',{}).get('answer_status',row.get('error')),row['seconds'],flush=True)
        finally:
            LLMClient.chat=original;LLMClient._one_call=raw_original
            # Windows 在连接池持有 SQLite 文件时无法清理临时数据库。
            from database.database import engine
            engine.dispose()
    print('completed',len(report['results']),flush=True)


if __name__=='__main__':main()
