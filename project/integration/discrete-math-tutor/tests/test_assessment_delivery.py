"""随机 PG 与厂家会话库的完成投递故障和重启边界。"""
import asyncio,json
from types import SimpleNamespace
from uuid import uuid4
import pytest
from tests.test_student_model_credentials import store

def test_durable_delivery_waits_for_completion_survives_delete_and_replays_once(store,tmp_path,monkeypatch):
 from integrations.deeptutor import assessment_delivery as delivery,assessment_jobs as jobs
 from deeptutor.services.session.sqlite_store import SQLiteSessionStore
 from deeptutor.services.session import sqlite_store
 native=SQLiteSessionStore(tmp_path/'delivery.db')
 owner='delivery-'+uuid4().hex[:8];vendor='vendor-'+owner
 async def prepare():
  await native.create_session(session_id='s')
 asyncio.run(prepare())
 with native._connect() as conn:
  conn.execute("INSERT INTO turns(id,session_id,status,created_at,updated_at) VALUES('t','s','running',0,0)")
 snapshot={'session_id':'s','turn_id':'t','workspace_id':'','answer':'学生真实原文','evaluation_control':jobs.evaluation_control(owner)}
 candidate=(owner,vendor,'s:1',snapshot)
 delivery.save(native,candidate)
 calls=[]
 monkeypatch.setattr(jobs,'enqueue',lambda *args:calls.append(args))
 delivery.drain_store(native,owner,vendor,'');assert not calls
 with native._connect() as conn:conn.execute("UPDATE turns SET status='completed' WHERE id='t'")
 monkeypatch.setattr(sqlite_store,'_session_delete_observer',delivery.before_delete)
 asyncio.run(native.delete_session('s'))
 def down(*args):raise RuntimeError('PG down')
 monkeypatch.setattr(jobs,'enqueue',down)
 with pytest.raises(RuntimeError):delivery.drain_store(native,owner,vendor,'')
 restarted=SQLiteSessionStore(native.db_path)
 monkeypatch.setattr(jobs,'enqueue',lambda *args:calls.append(args))
 delivery.drain_store(restarted,'other',vendor,'');assert not calls
 delivery.drain_store(restarted,owner,vendor,'')
 delivery.drain_store(restarted,owner,vendor,'')
 assert len(calls)==1 and calls[0][3]['answer']=='学生真实原文'

def test_off_then_on_fences_delayed_delivery_even_when_current_switch_is_on(store):
 from integrations.deeptutor import assessment_jobs as jobs
 owner='late-delivery-'+uuid4().hex[:8]
 control=jobs.evaluation_control(owner)
 jobs.set_enabled(owner,False);jobs.set_enabled(owner,True)
 assert jobs.evaluation_control(owner)['revision']==control['revision']+2
 assert jobs.enqueue(owner,'vendor','source',{'evaluation_control':control},'rule') is None
 assert jobs.recent_jobs(owner,'vendor')['jobs'][0]['status']=='cancelled'


def test_separate_process_recovers_queue_but_never_resends_unknown_provider_work(store,tmp_path):
 import os,subprocess,sys
 from pathlib import Path
 from tests.test_student_model_credentials import _save_verified
 from integrations.deeptutor import assessment_jobs as jobs
 from integrations.deeptutor.assessment_intake import confirmed_catalog,RULE_VERSION
 owner='restart-'+uuid4().hex[:8];vendor='vendor-'+owner
 _save_verified(store,owner,'https://8.8.8.8/v1','restart-model','fixture-only')
 catalog,version=confirmed_catalog();point=next(iter(catalog))
 snapshot={'catalog_version':version,'answer':'共同变化','targets':[{'id':point,'name':catalog[point]['name'],'source_ids':['s']}],
           'sources':[{'id':'s','text':'观察变量的共同变化。'}]}
 first=jobs.enqueue(owner,vendor,'crash-before-result',snapshot,RULE_VERSION)
 script=tmp_path/'consumer.py'
 script.write_text("""import os,sys,json,asyncio
from datetime import timedelta
from pathlib import Path
h=Path(sys.argv[1]);sys.path[:0]=[str(h),str(h.parents[1]/'vendor/DeepTutor'),str(h/'.runtime/browser-check-12d290667b/python-deps')]
sys.path.append('E:/项目/heart/project/integration/discrete-math-tutor/.venv-deeptutor/Lib/site-packages')
from integrations.deeptutor import assessment_jobs as jobs,assessment_worker as worker
assert jobs.credentials.engine.url.database==sys.argv[4]
owner=sys.argv[2];mode=sys.argv[3]
async def judge(dispatch,correction=''):
 if mode=='crash':os._exit(17)
 data=dispatch['input'];target=data['targets'][0]
 return json.dumps({'assessable':True,'knowledge_point_id':target['id'],'passed':True,'feedback':'隔离进程验证','answer_excerpt':data['answer'],'citations':[{'source_id':'s','quote':'观察变量的共同变化。'}]},ensure_ascii=False)
worker.judge=judge
if mode=='recover':
 assert jobs.claim(owner,now=jobs._now()+timedelta(seconds=91)) is None
else:
 assert asyncio.run(worker.run_one(owner))
""",encoding='utf-8')
 def child(mode):
  return subprocess.run([sys.executable,str(script),str(Path.cwd()),owner,mode,store.engine.url.database],env=os.environ.copy(),capture_output=True,timeout=80)
 assert child('crash').returncode==17
 assert jobs.status(owner,first)['status']=='sent'
 result=child('recover');assert result.returncode==0,result.stderr.decode(errors='replace')
 assert jobs.status(owner,first)['status']=='unknown'
 second=jobs.enqueue(owner,vendor,'queued-before-restart',snapshot,RULE_VERSION)
 result=child('finish');assert result.returncode==0,result.stderr.decode(errors='replace')
 assert jobs.status(owner,first)['status']=='unknown' and jobs.status(owner,first)['attempts']==1
 assert jobs.status(owner,second)['status']=='completed' and jobs.status(owner,second)['attempts']==1
