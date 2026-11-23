from pathlib import Path
import asyncio, json, os, secrets, shutil, socket, subprocess, sys, time, uuid
import httpx
from dotenv import load_dotenv
from cryptography.fernet import Fernet

ROOT=Path.cwd();VENDOR=ROOT.parents[1]/'vendor/DeepTutor';RUN=Path(__file__).resolve().parent
DEPS='E:/项目/heart/project/integration/discrete-math-tutor/.venv-deeptutor/Lib/site-packages'
sys.path[:0]=[str(ROOT),str(VENDOR),str(RUN/'python-deps')];sys.path.append(DEPS)
load_dotenv('E:/项目/heart/project/integration/discrete-math-tutor/.env')
from tests.pg_support import temp_databases
ASSETS=Path('E:/项目/heart/project/integration/discrete-math-tutor/knowledge/courses/experimental-psychology-3')
graph_database={key:value for key,value in os.environ.items() if key.startswith('POSTGRES_')}
with temp_databases('heart_task9_final') as databases:
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
    from scripts.provision_review_accounts import provision,read_credentials
    created,credential_path=provision(home);assert created==10
    passwords=read_credentials(credential_path)
    assert provision(home)[0]==0
    prepared=_course_documents(ASSETS);assert len(prepared[2])==11
    workspaces={}
    for name,password in passwords.items():
        uid=auth.get_user_info(name)['id']
        with user_context(CurrentUser(id=uid,username=name,role='user',scope=scope_for_user(uid,is_admin=False))):
            reading=import_course_reading(prepared)
        grant=learner_grant(uid);grant['learning_policy']['reading']['material_ids']=[m['material_id'] for m in reading['materials']]
        grant['learning_policy']['allowed_capabilities']=['chat','immersive_reading','mastery_path'];grant['learning_policy']['default_capability']='chat';save_grant(uid,grant);workspaces[name]=reading
    fixture={'accounts':list(passwords),'paths':{},'entries':[]}
    (home/'task9-fixture.json').write_text(json.dumps(fixture),encoding='utf-8')
    engine.dispose()
    with socket.socket() as host_socket:
        host_socket.bind(('127.0.0.1',0));host_port=host_socket.getsockname()[1]
    host_url=f'http://127.0.0.1:{host_port}'
    os.environ.update(DEEPTUTOR_HOST_URL=host_url,FIXED_BOOK_RETRIEVAL_ENABLED='0',CLEANUP_EXPIRED_ON_STARTUP='0')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    url=f'http://127.0.0.1:{port}';header={'x-heart-bridge-token':token}
    log_path=home/'worker.log'
    code = "import json,os,runpy,sys,time,asyncio,base64,hashlib,httpx\nfrom pathlib import Path\nr=Path(sys.argv[1]);sys.path[:0]=[str(r),str(r.parents[1]/'vendor/DeepTutor'),sys.argv[2]];sys.path.append(sys.argv[3])\nfrom types import SimpleNamespace\nfrom integrations.deeptutor import model_capabilities\nasync def invoke(dispatch):\n c=dispatch['capability']\n if c=='chat':content='HEART-'+dispatch['request_id'][:8]\n elif c=='vision':content=','.join(model_capabilities._vision_image(dispatch['request_id'])[1])\n elif c=='assessment':\n  values=[]\n  for i,sample in enumerate(model_capabilities.assessment_samples()):\n   values.append({'assessable':True,'knowledge_point_id':sample['targets'][0]['id'],'passed':i==0,'feedback':'隔离能力验证样例','answer_excerpt':sample['answer'],'citations':[{'source_id':'sample-source','quote':sample['sources'][0]['text']}]})\n  content=json.dumps({'judgments':values},ensure_ascii=False)\n else:raise ValueError('not used')\n with (Path(os.environ['DEEPTUTOR_HOME'])/'task9-probe-calls.jsonl').open('a',encoding='utf-8') as log:log.write(json.dumps({'owner':dispatch['student_id'],'capability':c,'model':dispatch['config']['model']})+chr(10))\n return SimpleNamespace(content=content)\nmodel_capabilities.invoke=invoke\nimport uvicorn\nworker=str(r/'integrations/deeptutor/worker.py');sys.argv=[worker,*sys.argv[4:]];runpy.run_path(worker,run_name='__main__')"
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
                HEART_BROWSER_DEMO=json.dumps(fixture),HEART_TEST_IMAGE_DIR=str(RUN),HEART_BROWSER_REPORT=str(RUN/'browser-task9-results.json'))
            host_code = """import sys, uvicorn
sys.path[:0]=[sys.argv[1],sys.argv[2],sys.argv[3]]
sys.path.append(sys.argv[4])
uvicorn.run('main:app',host='127.0.0.1',port=int(sys.argv[5]),access_log=False)"""
            with (home/'frontend.log').open('wb') as web_log,(home/'host.log').open('wb') as host_log:
                host=subprocess.Popen([sys.executable,'-c',host_code,str(ROOT),str(VENDOR),str(RUN/'python-deps'),DEPS,str(host_port)],
                    cwd=ROOT,env=launch,stdout=host_log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
                frontend=None
                try:
                    built=Path(json.loads((ROOT/'.runtime/task6-build.json').read_text('utf-8'))['web'])
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
                        raise RuntimeError('browser failed; inspect browser-task9-results.json and task8-failure-jobs.json')
                    proc.terminate();proc.wait(timeout=20)
                    assert (home/'task9-probe-calls.jsonl').is_file()
                    (RUN/'task9-integration-results.json').write_text(json.dumps({'accounts':10,'initialization_idempotent':True,'controlled_capability_boundary':True,'probe_calls':[json.loads(x) for x in (home/'task9-probe-calls.jsonl').read_text('utf-8').splitlines()]},indent=2),encoding='utf-8')
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
