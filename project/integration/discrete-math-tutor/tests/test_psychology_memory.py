"""同一学生ID的新旧课程数据库隔离；仅使用临时合成记录。"""
import hashlib,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class PsychologyMemoryTests(unittest.TestCase):
    def run_script(self,script,course,base):
        env=os.environ|{'TUTOR_COURSE':course,'DATABASE_URL':'sqlite:///'+str(base),'LLM_MOCK':'1'}
        env.pop('COURSE_DATABASE_URL',None)
        result=subprocess.run([sys.executable,'-X','utf8','-c',script],cwd=ROOT,env=env,
                              capture_output=True,text=True,encoding='utf-8',timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
        return result.stdout

    def test_restart_keeps_preferences_and_recalls_old_history_without_student_leak(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)/'restart.db'
            self.run_script('''
from database.database import init_db
from memory.memory_manager import MemoryManager
init_db();m=MemoryManager()
for sid in ['restart-a','restart-b']:m.ensure_student(sid)
m.set_preferences('restart-a',{'answer_length':.8,'example_density':.9,'learning_pace':.2})
m.set_active_goal('restart-a','自变量与因变量')
m.append('restart-a','user','我容易把自变量和因变量弄反，喜欢用做饭的例子解释。')
m.set_active_goal('restart-a','反应时法')
for n in range(35):m.append('restart-a','user','反应时法的无关进度记录'+str(n))
m.append('restart-b','user','自变量与因变量：B_ONLY_PRIVATE_MARKER，我喜欢用篮球例子。')
assert not any('做饭' in row['content'] for row in m.get_history('restart-a'))
''','experimental-psychology-3',base)
            output=self.run_script('''
import json
from memory.memory_manager import MemoryManager
m=MemoryManager()
profile=m.get_profile('restart-a')
assert profile.preferences['answer_length']==.8
assert profile.preferences['example_density']==.9
assert profile.preferences['learning_pace']==.2
overview=m.memory_overview('restart-a')
assert all(p['source']=='explicit_user' for p in overview['preferences'] if p['key'] in ['answer_length','example_density','learning_pace'])
context=m.retrieve_context('restart-a',title='自变量与因变量',question='自变量和因变量的区别，用做饭的例子')
assert context['preferences']['example_density']==.9
assert context['retrieval']['history_scope']=='all'
assert any('做饭' in row['content'] and row['source']['id'] for row in context['related_history'])
assert 'B_ONLY_PRIVATE_MARKER' not in json.dumps(context,ensure_ascii=False)
other=m.retrieve_context('restart-b',question='自变量和因变量的区别，用做饭的例子')
assert '我容易把自变量和因变量弄反' not in json.dumps(other,ensure_ascii=False)
assert '做饭' not in json.dumps(other.get('related_history',[]),ensure_ascii=False)
empty=m.retrieve_context('restart-new',question='自变量和因变量的区别')
assert empty['items']==[] and empty['preferences']=={}
print(json.dumps({'preferences_after_restart':'passed','old_history_beyond_window':'passed',
 'source_traceability':'passed','student_isolation_both_directions':'passed','new_student_no_invented_memory':'passed',
 'retrieval':context['retrieval']},ensure_ascii=False))
''','experimental-psychology-3',base)
            report=json.loads(output.strip().splitlines()[-1])
            report['method']='两个独立Python进程、独立SQLite、合成学生；未调用外部模型'
            (ROOT/'artifacts/psychology-cross-session-memory-acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')

    def test_background_jobs_resume_across_processes_without_restoring_deleted_memory(self):
        common = '''
import json
from database.database import init_db,session_scope
from database.models import MemoryJobRow,MemoryArtifactRow
from sqlalchemy import select,func
from memory.memory_manager import MemoryManager
from memory.background_worker import MemoryWorker,memory_lifespan
init_db();m=MemoryManager();point='自变量与因变量'
'''
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)/'background.db'
            self.run_script(common+'''
from uuid import uuid4
from models.student_state import StudentState
from models.lesson_plan import LessonPlan,LessonStep
from memory.evidence_policy import EvidenceDecision
from database.memory_jobs import utcnow
import datetime as dt
for sid in ['crashed','queued','deleted']:
 m.ensure_student(sid)
 state=StudentState(student_id=sid,current_concept=point)
 plan=LessonPlan(goal=point,steps=[LessonStep(step_id='S1',objective='区分变量')],current_step='S1')
 result=m.commit_learning_turn(student_id=sid,point=point,event_id=str(uuid4()),
  expected_token=m.get_version(sid,point),message=sid+'：我会把自变量和因变量弄混。',
  reply='合成验收解释',state=state,lesson_plan=plan,
  decision=EvidenceDecision(False,False,'仅记录提问'),evidence=[],hypotheses=[],
  strategy='example',success=None,instructional_move='worked_example')
 assert result['status']=='committed',result
 if sid=='crashed':
  claim=m.repo.claim_memory_job()
  assert claim['student_id']==sid
# 模拟进程已领取任务后退出；仅将测试库租约调到过去，不等待90秒。
with session_scope() as session:
 job=session.scalar(select(MemoryJobRow).where(MemoryJobRow.student_id=='crashed'))
 assert job.status=='running' and job.attempts==1
 job.lease_until=utcnow()-dt.timedelta(seconds=1)
m.forget_point('deleted',point)
''','experimental-psychology-3',base)
            self.run_script(common+'''
import asyncio,time
from types import SimpleNamespace
from unittest.mock import patch
app=SimpleNamespace(state=SimpleNamespace(memory=m,memory_llm=None))
async def resume():
 with patch.dict('os.environ',{'MEMORY_WORKER_ENABLED':'1','MEMORY_REFLECTION_LLM':'0'}):
  async with memory_lifespan(app):
   assert app.state.memory_worker.status()['running']
   deadline=time.monotonic()+5
   while time.monotonic()<deadline:
    with session_scope() as session:
     completed=session.scalar(select(func.count()).select_from(MemoryJobRow).where(MemoryJobRow.status=='completed'))
    if completed==2:break
    await asyncio.sleep(.05)
   assert completed==2,completed
 assert not app.state.memory_worker.status()['running']
asyncio.run(resume())
''','experimental-psychology-3',base)
            output=self.run_script(common+'''
for sid,attempts in [('queued',1),('crashed',2)]:
 memories=m.repo.background_memories(sid,point)
 assert len(memories)==1,memories
 assert memories[0]['content']['generation_mode']=='rule'
 assert memories[0]['content']['notes'][0]['quote']==sid+'：我会把自变量和因变量弄混。'
 with session_scope() as session:
  job=session.scalar(select(MemoryJobRow).where(MemoryJobRow.student_id==sid))
  assert job.status=='completed' and job.attempts==attempts
assert m.repo.background_memories('deleted',point)==[]
assert m.repo.background_memories('unrelated-student',point)==[]
assert m.repo.background_memories('queued','反应时法')==[]
assert MemoryWorker(m.repo).run_once() is False
with session_scope() as session:
 assert session.scalar(select(func.count()).select_from(MemoryArtifactRow))==2
 assert session.scalar(select(func.count()).select_from(MemoryJobRow).where(MemoryJobRow.student_id=='deleted'))==0
print(json.dumps({'queued_after_restart':'passed','expired_lease_after_restart':'passed',
 'deleted_memory_not_restored':'passed','source_quotes_persisted':'passed',
 'student_and_topic_isolation':'passed','no_duplicate_artifacts':'passed',
 'lifespan_worker_start_stop':'passed','method':'三个独立进程、临时心理学数据库、规则摘录；未调用外部模型'},ensure_ascii=False))
''','experimental-psychology-3',base)
            report=json.loads(output.strip().splitlines()[-1])
            (ROOT/'artifacts/psychology-background-memory-acceptance.json').write_text(
                json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')

    def test_same_student_is_isolated_and_old_database_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)/'learners.db'
            self.run_script('''
from database.database import init_db
from memory.memory_manager import MemoryManager
init_db();memory=MemoryManager();memory.ensure_student('same-student')
memory.append('same-student','user','旧数学课程：欧拉回路')
memory.set_active_goal('same-student','欧拉图')
memory.set_preferences('same-student',{'answer_length':0.8})
assert len(memory.get_history('same-student'))==1
''','discrete-math',base)
            before=hashlib.sha256(base.read_bytes()).hexdigest()
            self.run_script('''
from database.database import init_db,DATABASE_URL,course_database_url
from memory.memory_manager import MemoryManager
from database.account_manager import AccountManager
from unittest.mock import Mock
assert 'experimental-psychology-3' in DATABASE_URL
init_db();memory=MemoryManager()
assert memory.get_history('same-student')==[]
assert memory.get_active_goal('same-student') is None
memory.ensure_student('same-student');memory.append('same-student','user','心理学课程：被试间设计')
assert memory.get_state('same-student','被试间设计').skill_states==[]
assert len(memory.get_history('same-student'))==1
repo=Mock();assert AccountManager(repo).cleanup_after_code_update()==0
repo.clear_test_accounts_on_code_change.assert_not_called()
from unittest.mock import patch
with patch.dict('os.environ',{'COURSE_DATABASE_URL':'sqlite:///./same.db'}):
 try:
  course_database_url('sqlite:///./same.db')
  raise AssertionError('允许与旧课程复用同一数据库')
 except ValueError:pass
''','experimental-psychology-3',base)
            self.assertEqual(hashlib.sha256(base.read_bytes()).hexdigest(),before)
            self.assertTrue(base.with_name('learners.experimental-psychology-3.db').exists())

if __name__=='__main__':unittest.main()
