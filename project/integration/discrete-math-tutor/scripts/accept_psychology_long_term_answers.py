"""跨进程、跨会话真实回答验收；只使用合成记录及独立课程数据库。"""
import json,os,subprocess,sys,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
OUTPUT=ROOT/'artifacts/psychology-long-term-answer-acceptance.json'

def seed():
    from database.database import init_db
    from memory.memory_manager import MemoryManager
    init_db();memory=MemoryManager()
    records={'longterm-a':'我学自变量时容易弄混，最喜欢用番茄炒蛋、炒菜这样的做饭场景来解释。',
             'longterm-b':'我学自变量时容易弄混，最喜欢篮球投篮场景，不喜欢做饭例子。'}
    for sid,content in records.items():
        memory.ensure_student(sid)
        memory.set_preferences(sid,{'answer_length':.8,'example_density':.9,'learning_pace':.2})
        memory.set_active_goal(sid,'自变量')
        memory.append(sid,'user',content)
        memory.set_active_goal(sid,'反应时法')
        for n in range(35):memory.append(sid,'user','反应时章节的无关进度记录'+str(n))
        assert not any('最喜欢' in row['content'] for row in memory.get_history(sid))
    print('合成旧记录已保存并挤出短期窗口，准备结束旧进程。',flush=True)

def answer():
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env');load_dotenv(ROOT/'deepseek.env')
    from llm.client import LLMClient
    original=LLMClient.chat
    def bounded(self,*args,**kwargs):
        if kwargs.get('timeout') is None:kwargs['timeout']=35
        return original(self,*args,**kwargs)
    LLMClient.chat=bounded
    from fastapi.testclient import TestClient
    from main import app,orchestrator
    question='请结合教材解释自变量，按我以前喜欢的日常场景举个例子，不要让我重新填写偏好，并引用教材。'
    cases=[('长期偏好A','longterm-a',question),('另一学生B','longterm-b',question),
           ('当前要求优先','longterm-a','请结合教材解释自变量。这次不要按我以前的场景，改用跑步的例子，并引用教材。')]
    report={'method':'种子进程结束后，新进程调用原API；合成学生，独立学习库，真实模型，关闭图解以单独验收记忆',
            'database':os.environ['DATABASE_URL'],'cases':[]}
    with TestClient(app) as client:
        for name,sid,text in cases:
            context=orchestrator.memory.retrieve_context(sid,title='自变量',question=text)
            context_text=json.dumps(context,ensure_ascii=False)
            if sid=='longterm-a':assert '篮球投篮场景' not in context_text
            else:assert '番茄炒蛋' not in context_text
            started=time.monotonic();print('开始：'+name,flush=True)
            response=client.post('/api/chat',json={'student_id':sid,'account_type':'production','message':text,
                'session_id':'new-session-'+str(uuid.uuid4()),'request_id':str(uuid.uuid4())})
            result=response.json()
            report['cases'].append({'name':name,'question':text,'seconds':round(time.monotonic()-started,1),
                'http_status':response.status_code,'memory_before_turn':context,'result':result})
            OUTPUT.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
            print(json.dumps({'name':name,'status':result.get('answer_status'),'reply':result.get('reply')},ensure_ascii=False),flush=True)
    print('原始结果已保存；须人工核对场景、引用和记忆来源，不能只凭回答状态认定通过。',flush=True)

if __name__=='__main__':
    if len(sys.argv)>1:
        seed() if sys.argv[1]=='seed' else answer()
    else:
        run=str(time.time_ns())
        env=os.environ|{'TUTOR_COURSE':'experimental-psychology-3',
            'DATABASE_URL':'sqlite:///'+str(ROOT/f'artifacts/psychology-long-term-{run}.db'),
            'LLM_MOCK':'0','MEMORY_WORKER_ENABLED':'0','VISUALIZATION_ON_DEMAND':'0'}
        env.pop('COURSE_DATABASE_URL',None)
        for phase in ['seed','answer']:
            subprocess.run([sys.executable,'-X','utf8',str(Path(__file__).resolve()),phase],cwd=ROOT,env=env,check=True)
