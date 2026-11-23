from pathlib import Path
import asyncio, json, os, secrets, shutil, socket, subprocess, sys, time, uuid
import httpx
from dotenv import load_dotenv
from cryptography.fernet import Fernet

ROOT=Path.cwd();VENDOR=ROOT.parents[1]/'vendor/DeepTutor';RUN=Path(__file__).resolve().parent
DEPS='E:/项目/heart/project/integration/discrete-math-tutor/.venv-deeptutor/Lib/site-packages'
sys.path[:0]=[str(ROOT),str(VENDOR),str(RUN/'python-deps')];sys.path.append(DEPS)
load_dotenv('E:/项目/heart/project/integration/discrete-math-tutor/.env')
import types
tests=types.ModuleType('tests');tests.__path__=['E:\\项目\\heart\\.worktrees\\student-frontend-reuse-20261117\\project\\integration\\discrete-math-tutor\\tests'];sys.modules['tests']=tests
from tests.pg_support import temp_databases
ASSETS=Path('E:/项目/heart/project/integration/discrete-math-tutor/knowledge/courses/experimental-psychology-3')
graph_database={key:value for key,value in os.environ.items() if key.startswith('POSTGRES_')}
with temp_databases('heart_task10_joint') as databases:
    os.environ.update(databases)
    os.environ.update(graph_database)
    for key in tuple(os.environ):
        if 'API_KEY' in key or key in ('AUTH_PASSWORD_HASH','AUTH_USERNAME','POCKETBASE_URL'):
            os.environ[key]=''
    home=RUN/('full-worker-'+uuid.uuid4().hex[:8]);home.mkdir()
    os.environ['MEM0_HISTORY_PATH']=str(home/'mem0-history.sqlite')
    token=secrets.token_urlsafe(40)
    os.environ.update(TUTOR_PSYCHOLOGY_DIR=str(ASSETS),DEEPTUTOR_HOME=str(home),DEEPTUTOR_BRIDGE_TOKEN=token,
        HEART_MODEL_ENCRYPTION_KEY=Fernet.generate_key().decode(),DEEPTUTOR_NATIVE_ENABLED='1',HEART_WSL_SANDBOX_DISTRO='',
        MEM0_ENABLED='0',DEEPSEEK_API_KEY='local-unused-mem0-constructor',OPENAI_BASE_URL='http://127.0.0.1:1/v1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',RAG_EMBED_DEVICE='cpu',RAG_RERANK_DEVICE='cpu')
    from database.database import engine
    from sqlalchemy.engine import make_url
    assert engine.url.database==make_url(databases['COURSE_DATABASE_URL']).database
    from database.models import Base
    Base.metadata.create_all(engine)

    from deeptutor.services.path_service import get_path_service
    settings=get_path_service().get_settings_dir();settings.mkdir(parents=True,exist_ok=True)
    (settings/'auth.json').write_text('{"enabled":true}',encoding='utf-8')
    from deeptutor.services import auth
    from deeptutor.multi_user.models import CurrentUser
    from deeptutor.multi_user.paths import scope_for_user,user_context
    from deeptutor.multi_user.grants import learner_grant,save_grant
    from integrations.deeptutor.course_reading import _course_documents, import_course_reading
    auth.add_user('fixture-admin',secrets.token_urlsafe(28),role='admin')
    passwords={name:secrets.token_urlsafe(32) for name in ('heart-review-01','heart-review-02')}
    prepared=_course_documents(ASSETS);assert len(prepared[2])==11
    workspaces={}
    for name,password in passwords.items():
        auth.add_user(name,password,role='user',preset='learner');uid=auth.get_user_info(name)['id']
        with user_context(CurrentUser(id=uid,username=name,role='user',scope=scope_for_user(uid,is_admin=False))):
            reading=import_course_reading(prepared)
            if name == 'heart-review-01':
                from deeptutor.services.learning_journal import get_learning_journal_store
                journal=get_learning_journal_store()
                assert journal.set_mission(topic='隔离验收：实验设计',why='测试辅导交接',level='入门').accepted
                assert journal.note_session(summary='已讨论自变量',next_focus='继续学习因变量').accepted
                for number in range(26):
                    assert journal.add_record(title=f'验收记录 {number:02}',insight=f'独立的临时辅导记录 {number:02}，不是测评成绩。').accepted
        grant=learner_grant(uid);grant['learning_policy']['reading']['material_ids']=[m['material_id'] for m in reading['materials']]
        grant['learning_policy']['allowed_capabilities']=['chat','immersive_reading','mastery_path'];grant['learning_policy']['default_capability']='chat';save_grant(uid,grant);workspaces[name]=reading
    from integrations.deeptutor import model_credentials as credentials,model_capabilities as capabilities
    from integrations.deeptutor.catalog_binding import install_catalog_binding
    from integrations.deeptutor.heart_model_api import install_heart_model
    from fastapi import FastAPI
    install_heart_model(FastAPI(),home);install_catalog_binding()
    source_doc=json.loads((ASSETS/'chapters/chapter_03/document.json').read_text('utf-8'))
    source_map=json.loads((Path(os.environ['LIGHTRAG_CANDIDATE_PATH'])/'source_map.json').read_text('utf-8'))['chapter_03.generated.pdf']
    source_text='\n'.join(str(b.get('text','')) for b in source_doc['blocks'] if b.get('section_id')==1)[:1800]
    source={'source_id':'task8-source','type':'heart_textbook_evidence','document_id':source_map['document_id'],'version':source_map['version'],
        'quote':source_text,'text':source_text,'title':'第三章相关设计教材原文','chapter_id':3,'section_id':1,'index':1,
        'location':{'evidence':{'evidence_id':'task8-source','document_id':source_map['document_id'],'document_version':source_map['version'],'quote':source_text}}}
    fixture={'source':source,'paths':{},'entries':[],'real_vision':json.loads((RUN/'task8-real-vision.json').read_text('utf-8'))}
    from deeptutor.api.routers.mastery_path import create_topic,ConfirmTopicRequest
    from deeptutor.services.session import get_sqlite_session_store
    from deeptutor.learning.assessment import record_assessment,AssessmentRecord
    for index,name in enumerate(passwords):
        uid=auth.get_user_info(name)['id']
        credentials.save(name,'https://1.1.1.1/v1','review-alpha' if index==0 else 'review-beta','local-alpha-fixture' if index==0 else 'local-beta-fixture')
        version=credentials.read(name)['credential_version']
        for capability in ['chat','assessment','vision']:
            dispatch,_=capabilities.begin_check(name,uid,str(uuid.uuid4()),capability,version,confirm_cost=True)
            assert capabilities.finish_check(dispatch,'passed')
        if index:continue
        with user_context(CurrentUser(id=uid,username=name,role='user',scope=scope_for_user(uid,is_admin=False))):
            for point,title in [('kc-3-1','相关设计'),('kc-3-2','准实验设计')]:
                topic=asyncio.run(create_topic(ConfirmTopicRequest(name='TASK8-'+title,goal='隔离验收自编练习',sources=[{'id':'task8-topic-source-'+point,'kind':'file','source_id':source_map['document_id'],'label':'实际教材依据','excerpt':source_text,'metadata':{'document_id':source_map['document_id'],'version':source_map['version']}}],modules=[{'name':title,'knowledge_points':[{'id':point,'name':title,'type':'concept','topic_source_ids':['task8-topic-source-'+point]}]}])))
                path_id=topic['path_id'];fixture['paths'][point]=path_id
                session_id='task8-bank-'+point;store=get_sqlite_session_store()
                asyncio.run(store.create_session(title='TASK8 自编练习来源',session_id=session_id))
                record=asyncio.run(record_assessment(AssessmentRecord(session_id=session_id,turn_id='fixture-'+point,
                    question_id='task8-'+point,question='TASK8 自编练习 '+title+'：请选择与标题相符的设计。',question_type='single_choice',
                    options={'A':'不符合本题的设计','B':title},correct_answer='B',user_answer='A',explanation='这是隔离验收自编题，不是官方教材习题。',
                    source='mastery_path',result='incorrect',mastery_path_id=path_id,knowledge_point_id=point,
                    created_at=time.time()-2*86400,updated_at=time.time()-2*86400)))
                from deeptutor.services.practice.storage import PracticeStore
                practice = PracticeStore(store.db_path)
                with practice.connect() as conn:
                    historical = time.time() - 2*86400
                    conn.execute('UPDATE notebook_entries SET created_at=?, updated_at=? WHERE id=?', (historical, historical, record.entry_id))
                    conn.execute('UPDATE practice_review_state SET first_wrong_at=?, due_at=? WHERE entry_id=?', (historical, historical+86400, record.entry_id))
                assert record.entry_id;fixture['entries'].append({'id':record.entry_id,'point':point,'session_id':session_id})
    (home/'task8-fixture.json').write_text(json.dumps(fixture,ensure_ascii=False),encoding='utf-8')
    engine.dispose()
    with socket.socket() as host_socket:
        host_socket.bind(('127.0.0.1',0));host_port=host_socket.getsockname()[1]
    host_url=f'http://127.0.0.1:{host_port}'
    os.environ.update(DEEPTUTOR_HOST_URL=host_url,FIXED_BOOK_RETRIEVAL_ENABLED='0',CLEANUP_EXPIRED_ON_STARTUP='0')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    url=f'http://127.0.0.1:{port}';header={'x-heart-bridge-token':token}
    log_path=home/'worker.log'
    code = 'import json,os,runpy,sys,time,asyncio,base64,hashlib,httpx\nfrom pathlib import Path\nr=Path(sys.argv[1]);sys.path[:0]=[str(r),str(r.parents[1]/\'vendor/DeepTutor\'),sys.argv[2]];sys.path.append(sys.argv[3])\nfixture=json.loads((Path(os.environ[\'DEEPTUTOR_HOME\'])/\'task8-fixture.json\').read_text(\'utf-8\'))\nfrom integrations.deeptutor import heart_model_api,assessment_worker,screenshot_intake,practice_sync,assessment_jobs\n\ndef transport(base_url):\n async def reply(request):\n  payload=json.loads(request.content);model=payload.get(\'model\',\'fixture\')\n  assert request.headers.get(\'authorization\')=={\'review-alpha\':\'Bearer local-alpha-fixture\',\'review-beta\':\'Bearer local-beta-fixture\'}[model]\n  messages=payload.get(\'messages\',[])\n  last_user=max((i for i,m in enumerate(messages) if m.get(\'role\')==\'user\'),default=-1)\n  retrieved=any(m.get(\'role\')==\'tool\' for m in messages[last_user+1:])\n  common={\'id\':\'task8-fixture\',\'created\':int(time.time()),\'model\':model}\n  if not retrieved and any(t.get(\'function\',{}).get(\'name\')==\'rag\' for t in payload.get(\'tools\',[])):\n   delta={\'tool_calls\':[{\'index\':0,\'id\':\'task8-rag-call\',\'type\':\'function\',\'function\':{\'name\':\'rag\',\'arguments\':\'{"query":"相关设计","limit":1}\'}}]};finish=\'tool_calls\'\n  else:delta={\'role\':\'assistant\',\'content\':\'TASK8 辅导已完成。请根据教材继续说明变量关系。\'};finish=\'stop\'\n  if payload.get(\'stream\'):\n   frames=[{**common,\'object\':\'chat.completion.chunk\',\'choices\':[{\'index\':0,\'delta\':delta,\'finish_reason\':None}]},{**common,\'object\':\'chat.completion.chunk\',\'choices\':[{\'index\':0,\'delta\':{},\'finish_reason\':finish}]}]\n   return httpx.Response(200,headers={\'content-type\':\'text/event-stream\'},text=\'\'.join(\'data: \'+json.dumps(frame)+chr(10)*2 for frame in frames)+\'data: [DONE]\'+chr(10)*2)\n  return httpx.Response(200,json={**common,\'object\':\'chat.completion\',\'choices\':[{\'index\':0,\'message\':delta,\'finish_reason\':finish}]})\n return httpx.AsyncClient(transport=httpx.MockTransport(reply))\nheart_model_api.build_student_http_client=transport\nfrom integrations.deeptutor.heart_rag import HeartCourseRagTool\nfrom deeptutor.core.tool_protocol import ToolResult\nasync def rag(self,**kwargs):return ToolResult(content=\'TASK8-RAG-SOURCE \'+fixture[\'source\'][\'text\'],sources=[fixture[\'source\']])\nHeartCourseRagTool.execute=rag\nasync def recognize(config,text,images):\n digest=hashlib.sha256(base64.b64decode(images[0][\'image_url\'][\'url\'].split(\',\',1)[1])).hexdigest()\n case=next(c for c in fixture[\'real_vision\'][\'cases\'] if c[\'image_sha256\']==digest)\n return json.dumps(case[\'reading\'],ensure_ascii=False)\nscreenshot_intake.recognize=recognize\nasync def judge(dispatch,correction=\'\'):\n data=dispatch[\'input\'];target=data[\'targets\'][0];source=data[\'sources\'][0]\n record={\'job_id\':dispatch[\'id\'],\'model\':dispatch[\'config\'][\'model\'],\'correction\':correction,\'point\':target[\'id\']}\n with (Path(os.environ[\'DEEPTUTOR_HOME\'])/\'task8-model-calls.jsonl\').open(\'a\',encoding=\'utf-8\') as log:log.write(json.dumps(record)+chr(10))\n invalid=\'TASK8-WRONG-ID\' in data[\'answer\']\n return json.dumps({\'assessable\':True,\'knowledge_point_id\':\'invalid-point\' if invalid else target[\'id\'],\'passed\':True,\'feedback\':\'隔离模型按教材原文完成检查；不代表独立掌握。\',\'answer_excerpt\':data[\'answer\'][:120],\'citations\':[{\'source_id\':source[\'id\'],\'quote\':source[\'text\'][:100]}]},ensure_ascii=False)\nassessment_worker.judge=judge\noriginal_sync=practice_sync.sync;practice_fail=[True]\ndef sync(event,payload):\n if practice_fail[0]:practice_fail[0]=False;raise RuntimeError(\'controlled H sync outage\')\n return original_sync(event,payload)\npractice_sync.sync=sync\noriginal_publication=assessment_jobs.sync_publication;publication_fail=[True]\ndef publication(*args):\n if publication_fail[0]:publication_fail[0]=False;raise RuntimeError(\'controlled publication outage\')\n return original_publication(*args)\nassessment_jobs.sync_publication=publication\nimport uvicorn\noriginal_run=uvicorn.run\ndef serve(app,**options):\n from fastapi import Depends\n from deeptutor.api.routers.auth import require_auth\n @app.post(\'/api/test/task8/expire\',dependencies=[Depends(require_auth)])\n async def expire():\n  from integrations.deeptutor import attachment_retention as retention\n  from deeptutor.services.storage import get_attachment_store\n  store=get_attachment_store()\n  count=0\n  for path in store.root.glob(\'*/.heart-image-*.json\'):\n   row=retention.load(path);row[\'uploaded_at\']=time.time()-31*86400;retention.save(path,row);count+=1\n  retention.policy.prune(store)\n  return {\'controlled_fixture\':True,\'expired\':count}\n return original_run(app,**options)\nuvicorn.run=serve\nworker=str(r/\'integrations/deeptutor/worker.py\');sys.argv=[worker,*sys.argv[4:]];runpy.run_path(worker,run_name=\'__main__\')'
    with log_path.open('wb') as log:
        proc=subprocess.Popen([sys.executable,'-c',code,str(ROOT),str(RUN/'python-deps'),DEPS,'--home',str(home),'--port',str(port)],stdout=log,stderr=subprocess.STDOUT,env=os.environ.copy(),creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            for attempt in range(140):
                if proc.poll() is not None:raise RuntimeError('worker failed: '+log_path.read_text(encoding='utf-8',errors='replace')[-2200:])
                try:
                    if httpx.get(url+'/health/ready',timeout=1,trust_env=False).status_code==200:break
                except httpx.HTTPError:pass
                time.sleep(.5)
            else:raise RuntimeError('worker timed out')
            print('FULL_WORKER_READY',flush=True)
            def port_number():
                with socket.socket() as reserved:
                    reserved.bind(('127.0.0.1',0))
                    return reserved.getsockname()[1]
            web_port=port_number()
            base=f'http://127.0.0.1:{web_port}'
            host_url=f'http://127.0.0.1:{host_port}'
            launch=dict(os.environ,DEEPTUTOR_API_BASE_URL=url,BACKEND_PORT=str(port),
                HEART_API_BASE_URL=host_url,DEEPTUTOR_BACKEND_URL=url,DEEPTUTOR_HOST_URL=host_url,
                DEEPTUTOR_AUTOSTART='0',NEXT_PUBLIC_AUTH_ENABLED='true',DEEPTUTOR_AUTH_ENABLED='true',
                NEXT_PUBLIC_API_BASE_EXTERNAL=base,DEEPTUTOR_NEXT_DIST_DIR='.next',
                HEART_BROWSER_URL=base,HEART_BROWSER_WORKER=url,
                HEART_BROWSER_READING=json.dumps(workspaces),HEART_BROWSER_PASSWORDS=json.dumps(list(passwords.values())),
                HEART_BROWSER_DEMO=json.dumps(fixture),HEART_TEST_IMAGE_DIR=str(RUN),HEART_BROWSER_REPORT=str(RUN/'browser-task10-results.json'))
            host_code = """import sys, uvicorn
sys.path[:0]=[sys.argv[1],sys.argv[2],sys.argv[3]]
sys.path.append(sys.argv[4])
uvicorn.run('main:app',host='127.0.0.1',port=int(sys.argv[5]),access_log=False)"""
            with (home/'frontend.log').open('wb') as web_log,(home/'host.log').open('wb') as host_log:
                host=subprocess.Popen([sys.executable,'-c',host_code,str(ROOT),str(VENDOR),str(RUN/'python-deps'),DEPS,str(host_port)],
                    cwd=ROOT,env=launch,stdout=host_log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
                frontend=None
                try:
                    built=Path(json.loads(Path('E:\\项目\\heart\\.worktrees\\student-frontend-reuse-20261117\\project\\integration\\discrete-math-tutor\\.runtime\\task6-build.json').read_text('utf-8'))['web'])
                    standalone=built/'.next/standalone'
                    shutil.copytree(built/'.next/static',standalone/'.next/static',dirs_exist_ok=True)
                    if (built/'public').exists():shutil.copytree(built/'public',standalone/'public',dirs_exist_ok=True)
                    frontend=subprocess.Popen(['node','server.js'],cwd=standalone,env={**launch,'PORT':str(web_port),'HOSTNAME':'127.0.0.1'},stdout=web_log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
                    for attempt in range(120):
                        if frontend.poll() is not None or host.poll() is not None:
                            raise RuntimeError('frontend or host exited; inspect isolated frontend.log and host.log')
                        try:
                            if (httpx.get(base+'/login',timeout=5,trust_env=False).status_code==200
                                and httpx.get(host_url+'/health',timeout=2,trust_env=False).status_code==200):
                                break
                        except httpx.HTTPError:
                            pass
                        time.sleep(.5)
                    else:
                        raise RuntimeError('student site readiness timed out; inspect isolated frontend.log and host.log')
                    print('ISOLATED_FULL_STUDENT_SITE_READY',flush=True)
                    result=subprocess.run(['node','run.js',os.environ['HEART_BROWSER_SCRIPT']],
                        cwd='C:/Users/free/.agents/skills/playwright',env={**os.environ,**launch})
                    print('BROWSER_EXIT',result.returncode,'FRONTEND_EXIT',frontend.poll(),'HOST_EXIT',host.poll(),'WORKER_EXIT',proc.poll(),flush=True)
                    if result.returncode:
                        from integrations.deeptutor import assessment_jobs as diagnostic_jobs
                        diagnostic=diagnostic_jobs.recent_jobs('heart-review-01',auth.get_user_info('heart-review-01')['id'])
                        (RUN/'task8-failure-jobs.json').write_text(json.dumps(diagnostic,ensure_ascii=False,indent=2),encoding='utf-8')
                        raise RuntimeError('browser failed; inspect browser-task10-results.json and task8-failure-jobs.json')
                    proc.terminate();proc.wait(timeout=20)
                    from sqlalchemy import select,func
                    from database.models import LearningEventRow,AssessmentJobRow
                    from database.database import session_scope
                    from integrations.deeptutor import assessment_jobs as jobs
                    uid=auth.get_user_info('heart-review-01')['id']
                    with session_scope() as db:
                        reviews=db.scalars(select(LearningEventRow).where(LearningEventRow.student_id=='heart-review-01',LearningEventRow.event_type=='vendor_practice_review')).all()
                        completed=db.scalars(select(AssessmentJobRow).where(AssessmentJobRow.student_id=='heart-review-01',AssessmentJobRow.status=='completed')).all()
                        discarded=db.scalars(select(AssessmentJobRow).where(AssessmentJobRow.student_id=='heart-review-01',AssessmentJobRow.status=='discarded')).all()
                        assert reviews and completed and discarded
                        assert all((j.result or {}).get('publication_status')=='published' for j in completed)
                    calls=[json.loads(line) for line in (home/'task8-model-calls.jsonl').read_text('utf-8').splitlines()]
                    (RUN/'task10-integration-results.json').write_text(json.dumps({'controlled_model':True,'review_events':len(reviews),'completed':len(completed),'discarded':len(discarded),'calls':calls,'default_evaluation_enabled':jobs.get_enabled('heart-review-02')['enabled'],'real_vision_artifact_replayed':True},ensure_ascii=False,indent=2),encoding='utf-8')
                finally:
                    if frontend is not None and frontend.poll() is None:
                        subprocess.run(['taskkill','/PID',str(frontend.pid),'/T','/F'],capture_output=True)
                    if host.poll() is None:
                        host.terminate()
                        try:host.wait(timeout=12)
                        except subprocess.TimeoutExpired:host.kill();host.wait(timeout=10)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:proc.wait(timeout=15)
                except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=10)
