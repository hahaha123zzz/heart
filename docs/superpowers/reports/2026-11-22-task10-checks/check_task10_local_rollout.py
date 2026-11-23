from pathlib import Path
import os,sys,json,shutil,subprocess,hashlib,tarfile,time,uuid,re
from urllib.parse import urlsplit,unquote,quote
import psycopg,httpx
from dotenv import dotenv_values,load_dotenv
h=Path.cwd();root=h.parents[2]/'.runtime/student-release-20261122';private=root/'private';control=root/'control';old=root/'releases/candidate-runtime';new=root/'releases/local8000';run=h/'.runtime'
load_dotenv('E:/项目/heart/project/integration/discrete-math-tutor/.env')
for name in ['student_release.py','run_student_release.py','manage_student_local.py']:shutil.copy2(h/'deploy'/name,control/name)
sys.path[:0]=[str(control),str(h)]
from student_release import verify,select,HROOT,VROOT
from tests.pg_support import temp_databases
values={k:v for k,v in dotenv_values(private/'runtime.env').items() if isinstance(v,str)}
old_id=json.loads((old/'release.json').read_text('utf-8'))['release_id'];new_id=verify(new)['release_id']
shutil.copytree(old/VROOT/'web/.next/standalone',new/VROOT/'web/.next/standalone',dirs_exist_ok=True)
manager=[sys.executable,str(control/'manage_student_local.py')]
def managed(action):
 started=time.monotonic()
 result=subprocess.run([*manager,action,'--root',str(root)],capture_output=True,timeout=420)
 if result.returncode:raise RuntimeError('local service action failed:'+action+'; private logs retain details')
 return round(time.monotonic()-started,2)
def login():
 name,password=(Path(values['DEEPTUTOR_HOME'])/'.runtime/review-accounts/vendor-accounts.txt').read_text('utf-8').splitlines()[0].split('\t')
 with httpx.Client(base_url='http://127.0.0.1:8000',trust_env=False,timeout=30) as client:
  response=client.post('/api/auth/login',json={'username':name,'password':password});assert response.status_code==200
  return client.cookies.get('dt_token')
def request(method,path,token,body=None):
 with httpx.Client(base_url='http://127.0.0.1:8000',trust_env=False,timeout=30,cookies={'dt_token':token}) as client:
  response=client.request(method,path,json=body) if body is not None else client.request(method,path)
  assert response.status_code==200,(method,path,response.status_code)
  return response.json()
def pg(url):return url.replace('postgresql+psycopg://','postgresql://',1)
def pg_command(url):
 parts=urlsplit(pg(url));return ['--host',parts.hostname,'--port',str(parts.port or 5432),'--username',unquote(parts.username or ''),'--dbname',parts.path.lstrip('/')],dict(os.environ,PGPASSWORD=unquote(parts.password or ''))
rag=values.get('POSTGRES_DATABASE_URL') or 'postgresql://'+quote(values.get('POSTGRES_USER','heart'),safe='')+':'+quote(values.get('POSTGRES_PASSWORD',''),safe='')+'@'+values['POSTGRES_HOST']+':'+values.get('POSTGRES_PORT','5432')+'/'+values['POSTGRES_DATABASE']
urls={'business':values['DATABASE_URL'],'course':values['COURSE_DATABASE_URL'],'rag':rag};pgbin=Path('C:/Program Files/PostgreSQL/18/bin');home=Path(values['DEEPTUTOR_HOME']);backup=private/'backups'/('local-cutover-'+uuid.uuid4().hex[:8]);backup.mkdir(parents=True)
result={'old_release':old_id,'new_release':new_id,'scope':'localhost:8000 only','production_ecs_changed':False,'phase_seconds':{}}
try:
 result['phase_seconds']['initial_stop']=managed('stop');print('LOCAL_THREE_SERVICES_STOPPED',flush=True)
 # 迁出首次启动的教材坐标缓存；它是派生数据，不是源码或学生成绩。
 extra=old/HROOT/'.runtime/fixed-book'
 if extra.exists():
  for file in extra.rglob('*'):
   if not file.is_file():continue
   target=home/'.runtime/fixed-book'/file.relative_to(extra)
   if target.exists():target=home/'.runtime/migrated-citation-cache'/file.relative_to(extra)
   assert file.resolve().is_relative_to(old.resolve()) and target.resolve().is_relative_to(home.resolve())
   target.parent.mkdir(parents=True,exist_ok=True);file.rename(target)
 verify(old);verify(new)
 with tarfile.open(backup/'worker-home.tar.gz','w:gz',compresslevel=1) as archive:archive.add(home,arcname='worker-home')
 shutil.copy2(private/'runtime.env',backup/'runtime.env')
 for role,url in urls.items():
  args,env=pg_command(url);dump=backup/(role+'.dump')
  done=subprocess.run([str(pgbin/'pg_dump.exe'),*args,'--format=custom','--no-owner','--file',str(dump)],env=env,capture_output=True)
  if done.returncode:raise RuntimeError('pg_dump failed for '+role)
 hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in backup.iterdir() if p.is_file()}
 manifest=backup/'manifest.json';manifest.write_text(json.dumps({'files':hashes,'scope':'private local data backup; secret values omitted'},indent=2),'utf-8')
 result['backup_manifest_sha256']=hashlib.sha256(manifest.read_bytes()).hexdigest();result['private_backup_path']=str(backup)
 print('ACTUAL_LOCAL_HOME_KEYS_AND_THREE_DATABASES_BACKED_UP',flush=True)
 with temp_databases('heart_local_restore_verify') as target:
  destinations={'business':target['DATABASE_URL'],'course':target['COURSE_DATABASE_URL'],'rag':target['POSTGRES_DATABASE_URL']}
  for role,url in destinations.items():
   args,env=pg_command(url);dump=backup/(role+'.dump');listing=subprocess.check_output([str(pgbin/'pg_restore.exe'),'--list',str(dump)])
   filtered=re.sub(rb'(?m)^(\d+; \d+ \d+ COMMENT - EXTENSION vector *\r?)$',rb';\1',listing)
   toc=backup/(role+'.restore.list');toc.write_bytes(filtered)
   done=subprocess.run([str(pgbin/'pg_restore.exe'),*args,'--single-transaction','--exit-on-error','--no-owner','--use-list',str(toc),str(dump)],env=env,capture_output=True)
   if done.returncode:raise RuntimeError('isolated pg_restore failed for '+role)
  with psycopg.connect(pg(destinations['course'])) as connection:assert connection.execute("SELECT count(*) FROM students WHERE student_id LIKE 'heart-review-%'").fetchone()[0]==10
  graph=json.loads((new/HROOT/'knowledge/graph_release.json').read_text('utf-8'))
  with psycopg.connect(pg(destinations['rag'])) as connection:
   assert connection.execute('SELECT count(*) FROM lightrag_graph_nodes WHERE workspace=%s',(graph['workspace'],)).fetchone()[0]==7138
   assert connection.execute('SELECT count(*) FROM lightrag_graph_edges WHERE workspace=%s',(graph['workspace'],)).fetchone()[0]==14741
 result['actual_three_database_restore_verified']=True;result['restored_graph_nodes']=7138;result['restored_graph_edges']=14741
 print('ACTUAL_LOCAL_BACKUPS_RESTORED_IN_NEW_DATABASES',flush=True)
 select(root,new,old_id);result['phase_seconds']['new_start']=managed('start');print('LOCAL_NEW_RELEASE_READY',flush=True)
 token=login();text='本机切换回退验收：先给结论，再解释。'
 saved=request('POST','/api/heart/memory/preference',token,{'text':text});card=next(c for c in saved['preferences'] if c['text']==text);ident=card['id'];result['controlled_new_record_id']=ident
 managed('stop');select(root,old,new_id);result['phase_seconds']['rollback_start']=managed('start')
 assert any(c['id']==ident and c['text']==text for c in request('GET','/api/heart/memory',token)['preferences']);result['new_record_survived_rollback']=True
 print('ACTUAL_ROLLBACK_PRESERVED_NEW_RECORD_AND_LOGIN_SESSION',flush=True)
 managed('stop');select(root,new,old_id);result['phase_seconds']['relaunch_start']=managed('start')
 assert any(c['id']==ident and c['text']==text for c in request('GET','/api/heart/memory',token)['preferences']);result['new_record_survived_relaunch']=True
 request('DELETE','/api/heart/memory/preference/'+str(ident),token);assert not request('GET','/api/heart/memory',token)['preferences']
 result['controlled_record_removed_from_active_view']=True
 frozen=json.loads((run/'task10-assets.json').read_text('utf-8'));assets=Path(frozen['asset_root'])
 assert all(hashlib.sha256((assets/f['path']).read_bytes()).hexdigest()==f['sha256'] for f in frozen['files']);result['textbook_assets_unchanged']=True
 verify(old);verify(new);result['source_snapshots_still_verified']=True
 result['ready']=True;(run/'task10-local-rollout.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
 print('LOCAL_8000_FINAL_RELEASE_READY_DATA_RETAINED',flush=True)
except BaseException:
 try:managed('start')
 except Exception:pass
 raise
