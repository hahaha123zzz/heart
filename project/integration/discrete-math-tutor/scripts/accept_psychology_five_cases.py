"""五类真实验收：原API、独立学习库、合成学生；保留每轮原始结果供人工核对。"""
import json, os, sys, time, uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env');load_dotenv(ROOT/'deepseek.env')
RUN=str(time.time_ns())
os.environ.update(TUTOR_COURSE='experimental-psychology-3', LLM_MOCK='0',
    DATABASE_URL='sqlite:///'+str(ROOT/f'artifacts/psychology-five-{RUN}.sqlite3'),
    MEMORY_WORKER_ENABLED='0', VISUALIZATION_ON_DEMAND='1')
os.environ.pop('COURSE_DATABASE_URL',None)

from llm.client import LLMClient
original_chat=LLMClient.chat
def bounded_chat(self,*args,**kwargs):
    if kwargs.get('timeout') is None:kwargs['timeout']=35
    return original_chat(self,*args,**kwargs)
LLMClient.chat=bounded_chat
from fastapi.testclient import TestClient
from main import app,orchestrator
from knowledge.pdf_reader import document_for_chapter, PDFSelection, validate_selection
import fitz
from knowledge.pdf_reader import pdf_path

def main():
    record=document_for_chapter(7)
    with fitz.open(pdf_path(record)) as pdf:
        page=pdf[9]
        rect={'page':10,'x1':84/page.rect.width,'x2':513/page.rect.width,
              'y1':104/page.rect.height,'y2':248/page.rect.height}
    selection={'document_id':record['document_id'],'version':record['version'],'kind':'area','rects':[rect]}
    cases=[
        ('概念解释',['请结合教材解释自变量、因变量和额外变量的区别，并引用各自的教材依据。'],None),
        ('设计比较',['请结合教材比较被试间设计与被试内设计：每名被试接受几个处理水平，各自适合什么情况，有什么需要控制的问题？请引用教材。'],None),
        ('教材表格与自动图解',['请结合第四章表4-5，解释单因素随机区组设计如何分配被试，为什么能控制个体差异。'],None),
        ('公式区域圈选',['请解释我框选的两个差别感觉阈限DL公式：X、St、PSE、N分别是什么，两个公式的参照点有什么区别？引用这个选区，不要编造实验数据。'],selection),
        ('连续追问与记忆',['请结合教材解释什么是自变量。我喜欢日常生活中的例子，请一次只讲一个要点。',
                        '没听懂，请换一种更简单的说法。',
                        '请按照我刚才说的偏好，换一个日常生活例子，仍然只解释刚才那个概念。'],None),
    ]
    report={'run':RUN,'database':os.environ['DATABASE_URL'],'cases':[]}
    output=ROOT/'artifacts/psychology-five-cases-acceptance.json'
    with TestClient(app) as client:
        for number,(name,questions,selected) in enumerate(cases,1):
            case={'number':number,'name':name,'turns':[]};report['cases'].append(case)
            sid=f'psy-five-{RUN}-{number}'
            for turn,question in enumerate(questions,1):
                print(json.dumps({'case':number,'turn':turn,'stage':'开始','name':name},ensure_ascii=False),flush=True)
                payload={'student_id':sid,'account_type':'test','message':question,
                         'session_id':f'accept-{RUN}-{number}','request_id':str(uuid.uuid4())}
                if selected:payload['selection']=selected
                start=time.perf_counter()
                try:
                    response=client.post('/api/chat',json=payload)
                    result=response.json()
                    checks={'http_ok':response.status_code==200,'answered':result.get('answer_status')=='answered',
                            'has_citations':bool(result.get('pdf_references') or result.get('selection_ref'))}
                    for reference in result.get('pdf_references',[]):
                        ref=reference['selection_ref']
                        validate_selection(PDFSelection(**{k:ref[k] for k in ['document_id','version','kind','rects']}))
                    case['turns'].append({'question':question,'elapsed_seconds':round(time.perf_counter()-start,1),
                                          'checks':checks,'result':result})
                except Exception as error:
                    case['turns'].append({'question':question,'error':type(error).__name__,'checks':{'completed':False}})
                output.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
                latest=case['turns'][-1]
                print(json.dumps({'case':number,'turn':turn,'checks':latest['checks'],
                    'seconds':latest.get('elapsed_seconds'),'guide':bool(latest.get('result',{}).get('guided_visualization'))},ensure_ascii=False),flush=True)
            if number==5:
                case['synthetic_history']=orchestrator.memory.get_history(sid)
                output.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    print('验收结果已保存，需人工核对原文与回答，不能仅凭checks视为事实通过。',flush=True)

if __name__=='__main__':main()
