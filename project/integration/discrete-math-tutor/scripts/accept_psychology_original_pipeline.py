"""真实验收原Agent链路，仅发送合成问题与正式教材片段。"""
import json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env');load_dotenv(ROOT/'deepseek.env')
os.environ['TUTOR_COURSE']='experimental-psychology-3'
os.environ['DATABASE_URL']='sqlite:///'+str(ROOT/'artifacts/psychology-original-acceptance-base.sqlite3')
os.environ.pop('COURSE_DATABASE_URL',None)
os.environ['LLM_MOCK']='0'
from llm.client import LLMClient,LLMError
from orchestrator import TutorOrchestrator

class BoundedClient(LLMClient):
    def chat(self,*args,**kwargs):
        if kwargs.get('timeout') is None:kwargs['timeout']=35
        return super().chat(*args,**kwargs)

def main():
    tutor=TutorOrchestrator(llm=BoundedClient())
    run=str(time.time_ns());results=[]
    questions=['请解释什么是自变量、因变量，它们有什么区别，并引用教材。',
               '请结合教材解释单因素随机区组设计为什么能控制被试的个体差异。']
    for index,question in enumerate(questions):
        sid='psych-accept-'+run+'-'+str(index)
        start=time.perf_counter()
        def progress(stage,label,detail=''):print(json.dumps({'case':index+1,'stage':stage,'label':label},ensure_ascii=False),flush=True)
        try:
            result=tutor.handle_turn(sid,question,account_type='test',progress=progress)
        except LLMError:
            result={'answer_status':'llm_unavailable','reply':'模型调用未完成'}
        results.append({'question':question,'elapsed_seconds':round(time.perf_counter()-start,1),**result})
        (ROOT/'artifacts/psychology-original-pipeline-acceptance.json').write_text(json.dumps(results,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
        print(json.dumps({'case':index+1,'status':result.get('answer_status'),'references':len(result.get('pdf_references',[]))},ensure_ascii=False),flush=True)
    assert all(r.get('answer_status')=='answered' and r.get('pdf_references') for r in results),'原链路真实验收未全部通过，请检查结果'

if __name__=='__main__':main()
