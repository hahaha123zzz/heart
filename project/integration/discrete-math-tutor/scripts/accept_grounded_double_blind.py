"""重放原双盲四轮问题；隔离学生库，保存真实模型及全部引用，不隐藏失败。"""
import argparse,json,os,tempfile,time
from pathlib import Path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--index',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('报告已存在，不覆盖')
    original=json.loads(Path('artifacts/citation-grounding/known-failure/original.json').read_text(encoding='utf-8'))
    rows=[]
    with tempfile.TemporaryDirectory(prefix='grounded-doubleblind-') as directory:
        os.environ.update(TUTOR_COURSE='experimental-psychology-3',LLM_MOCK='0',MEMORY_WORKER_ENABLED='0',VISUALIZATION_ON_DEMAND='0',
            COURSE_DATABASE_URL='sqlite:///'+str(Path(directory)/'test.db'),CITATION_GROUNDING_MODE='active',CITATION_GROUNDING_INDEX=str(args.index.resolve()))
        from main import _run_turn,orchestrator
        from models.chat_request import ChatRequest
        from database.database import engine
        from llm.client import LLMClient
        assert not orchestrator.llm.mock
        call=LLMClient._one_call;calls=[]
        def measured(client,messages,*pos,**kw):
            started=time.monotonic();row={'agent':str(messages[0].get('content',''))[:60]};calls.append(row)
            try:
                text,finish=call(client,messages,*pos,**kw);row.update(response=text,finish_reason=finish);return text,finish
            finally:row['seconds']=round(time.monotonic()-started,3)
        LLMClient._one_call=measured
        try:
            for number,turn in enumerate(original['turns'],1):
                started=time.monotonic();calls.clear();row={'turn':turn['turn'],'message':turn['message']}
                try:
                    result=_run_turn(ChatRequest(student_id='grounded-doubleblind-v2',session_id='doubleblind',request_id=f'doubleblind-{number}',
                        message=turn['message'],reader_location={'chapter_id':2,'section_id':4}))
                    row['result']=result
                    row['has_definition_evidence']=any(ref.get('evidence',{}).get('source_block_id')==235 for ref in result.get('pdf_references',[]))
                except Exception as exc:row['error']={'type':type(exc).__name__,'message':str(exc)}
                row.update(seconds=round(time.monotonic()-started,3),calls=list(calls));rows.append(row)
                args.output.write_text(json.dumps({'method':'真实模型四轮；非教师审核','turns':rows},ensure_ascii=False,indent=2),encoding='utf-8')
                print(row['turn'],row.get('result',{}).get('answer_status',row.get('error')),row.get('has_definition_evidence'),flush=True)
        finally:LLMClient._one_call=call;engine.dispose()


if __name__=='__main__':main()
