from pathlib import Path
import asyncio, json, os, secrets, socket, subprocess, sys, time, uuid
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
with temp_databases('heart_task6_final') as databases:
    os.environ.update(databases)
    os.environ.update(graph_database)
    for key in tuple(os.environ):
        if 'API_KEY' in key or key in ('AUTH_PASSWORD_HASH','AUTH_USERNAME','POCKETBASE_URL'):
            os.environ[key]=''
    home=RUN/('full-worker-'+uuid.uuid4().hex[:8]);home.mkdir()
    token=secrets.token_urlsafe(40)
    os.environ.update(TUTOR_PSYCHOLOGY_DIR=str(ASSETS),DEEPTUTOR_HOME=str(home),DEEPTUTOR_BRIDGE_TOKEN=token,
        HEART_MODEL_ENCRYPTION_KEY=Fernet.generate_key().decode(),DEEPTUTOR_NATIVE_ENABLED='1',HEART_WSL_SANDBOX_DISTRO='',
        MEM0_ENABLED='0',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',RAG_EMBED_DEVICE='cpu',RAG_RERANK_DEVICE='cpu')
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
    engine.dispose()
    with socket.socket() as host_socket:
        host_socket.bind(('127.0.0.1',0));host_port=host_socket.getsockname()[1]
    host_url=f'http://127.0.0.1:{host_port}'
    os.environ.update(DEEPTUTOR_HOST_URL=host_url,FIXED_BOOK_RETRIEVAL_ENABLED='0',CLEANUP_EXPIRED_ON_STARTUP='0')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    url=f'http://127.0.0.1:{port}';header={'x-heart-bridge-token':token}
    log_path=home/'worker.log'
    code = r"""import json, runpy, sys, time, httpx
from pathlib import Path
r=Path(sys.argv[1]); sys.path[:0]=[str(r),str(r.parents[1]/'vendor/DeepTutor'),sys.argv[2]]; sys.path.append(sys.argv[3])
from integrations.deeptutor import heart_model_api

def transport(base_url):
    def reply(request):
        payload=json.loads(request.content)
        model=payload.get('model','fixture')
        key=request.headers.get('authorization','')
        expected={'review-alpha':'Bearer local-alpha-fixture','review-beta':'Bearer local-beta-fixture'}
        if expected.get(model)!=key:
            return httpx.Response(401,json={'error':{'message':'fixture credential mismatch'}})
        text='已收到你的教材问题。' if model=='review-alpha' else '第二个账号的独立辅导结果。'
        common={'id':'fixture','created':int(time.time()),'model':model}
        if payload.get('stream'):
            frames=[{**common,'object':'chat.completion.chunk','choices':[{'index':0,'delta':{'role':'assistant','content':text},'finish_reason':None}]},
                    {**common,'object':'chat.completion.chunk','choices':[{'index':0,'delta':{},'finish_reason':'stop'}]}]
            return httpx.Response(200,headers={'content-type':'text/event-stream'},text=''.join('data: '+json.dumps(frame)+'\n\n' for frame in frames)+'data: [DONE]\n\n')
        return httpx.Response(200,json={**common,'object':'chat.completion','choices':[{'index':0,'message':{'role':'assistant','content':text},'finish_reason':'stop'}]})
    return httpx.AsyncClient(transport=httpx.MockTransport(reply))
heart_model_api.build_student_http_client=transport
worker=str(r/'integrations/deeptutor/worker.py');sys.argv=[worker,*sys.argv[4:]];runpy.run_path(worker,run_name='__main__')"""
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
                HEART_BROWSER_DEMO=json.dumps({'accounts':[],'mode':'empty-account UI regression; actual scores captured in prior run'}),HEART_BROWSER_REPORT=str(RUN/'browser-task6-final-results.json'))
            host_code = """import sys, uvicorn
sys.path[:0]=[sys.argv[1],sys.argv[2],sys.argv[3]]
sys.path.append(sys.argv[4])
uvicorn.run('main:app',host='127.0.0.1',port=int(sys.argv[5]),access_log=False)"""
            with (home/'frontend.log').open('wb') as web_log,(home/'host.log').open('wb') as host_log:
                host=subprocess.Popen([sys.executable,'-c',host_code,str(ROOT),str(VENDOR),str(RUN/'python-deps'),DEPS,str(host_port)],
                    cwd=ROOT,env=launch,stdout=host_log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
                frontend=None
                try:
                    frontend=subprocess.Popen(['node','node_modules/next/dist/bin/next','start','--hostname','127.0.0.1','--port',str(web_port)],
                        cwd=Path(json.loads((ROOT/'.runtime/task6-build.json').read_text('utf-8'))['web']),env=launch,stdout=web_log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
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
                    if result.returncode:
                        raise RuntimeError('browser verification failed; see browser-task6-final-results.json')
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
