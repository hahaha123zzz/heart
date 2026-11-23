from pathlib import Path
import asyncio, json, os, secrets, socket, subprocess, sys, time, uuid
from contextlib import contextmanager
import hashlib, re, tarfile
from urllib.parse import urlsplit, unquote
import psycopg
import websockets
import httpx
from dotenv import load_dotenv
from cryptography.fernet import Fernet

ROOT=Path.cwd();VENDOR=ROOT.parents[1]/'vendor/DeepTutor';RUN=Path(__file__).resolve().parent
DEPS='E:/项目/heart/project/integration/discrete-math-tutor/.venv-deeptutor/Lib/site-packages'
sys.path[:0]=[str(ROOT),str(VENDOR),str(RUN/'python-deps')];sys.path.append(DEPS)
load_dotenv('E:/项目/heart/project/integration/discrete-math-tutor/.env')
from tests.pg_support import temp_databases
ASSETS=Path('E:/项目/heart/project/integration/discrete-math-tutor/knowledge/courses/experimental-psychology-3')
with temp_databases('heart_restore_src') as databases:
    os.environ.update(databases)
    for key in tuple(os.environ):
        if 'API_KEY' in key or key in ('AUTH_PASSWORD_HASH','AUTH_USERNAME','POCKETBASE_URL'):
            os.environ[key]=''
    rehearsal=RUN/('backup-rehearsal-'+uuid.uuid4().hex[:8]);rehearsal.mkdir()
    home=rehearsal/'source-home';home.mkdir()
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
        grant=learner_grant(uid);grant['learning_policy']['reading']['material_ids']=[m['material_id'] for m in reading['materials']]
        grant['learning_policy']['default_capability']='chat';save_grant(uid,grant);workspaces[name]=reading
    engine.dispose()
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

    from urllib.parse import urlsplit

    pg_bin = Path('C:/Program Files/PostgreSQL/18/bin')
    db_roles = {
        'business': 'DATABASE_URL',
        'course': 'COURSE_DATABASE_URL',
        'rag': 'POSTGRES_DATABASE_URL',
    }
    names = list(passwords)
    owner, other = names
    wid = workspaces[owner]['workspace_id']
    mid = workspaces[owner]['active_material_id']
    questions = ('请解释教材里的自变量。', '恢复后，请再解释一次因变量。')
    preference = '请先用生活案例，再解释术语。'
    bridge = {'x-heart-bridge-token': token}

    def pg_target(env, role, stage):
        value = urlsplit(env[db_roles[role]].replace('postgresql+psycopg://', 'postgresql://', 1))
        db = value.path.removeprefix('/')
        assert value.hostname in ('127.0.0.1', 'localhost', '::1')
        assert re.fullmatch(rf'heart_restore_{stage}(?:_course|_rag)?_[0-9a-f]{{10}}', db), db
        return value, db

    def pg_args(env, role, stage):
        parts, db = pg_target(env, role, stage)
        args = ['--host', parts.hostname, '--port', str(parts.port or 5432),
            '--username', unquote(parts.username), '--dbname', db, '--no-password']
        child_env = dict(os.environ, PGPASSWORD=unquote(parts.password or ''))
        return args, child_env

    def connect(env, role, stage):
        parts, db = pg_target(env, role, stage)
        return psycopg.connect(host=parts.hostname, port=parts.port or 5432,
            user=unquote(parts.username), password=unquote(parts.password or ''), dbname=db)

    @contextmanager
    def worker(path, env, log_name):
        with socket.socket() as reserved:
            reserved.bind(('127.0.0.1',0))
            port = reserved.getsockname()[1]
        url = f'http://127.0.0.1:{port}'
        log_path = rehearsal / log_name
        with log_path.open('wb') as log:
            proc = subprocess.Popen([sys.executable, '-X', 'utf8', '-c', code, str(ROOT),
                str(RUN/'python-deps'), DEPS, '--home', str(path), '--port', str(port)],
                env=dict(os.environ, **env), stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                for _ in range(155):
                    if proc.poll() is not None:
                        raise RuntimeError(f'worker stopped; see {log_path.name}')
                    try:
                        if httpx.get(url+'/health/ready',timeout=1,trust_env=False).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(.5)
                else:
                    raise TimeoutError(f'worker readiness; see {log_path.name}')
                yield url
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=10)

    def login(client, name):
        logged = client.post('/api/auth/login', json={'username':name,'password':passwords[name]})
        assert logged.status_code == 200, logged.status_code

    def pdf_digest(client):
        pdf = client.get(f'/api/reading/materials/{mid}/raw')
        assert pdf.status_code == 200 and pdf.content.startswith(b'%PDF')
        return hashlib.sha256(pdf.content).hexdigest()

    async def turn(client, url, session, question):
        headers = {**bridge, 'Cookie': 'dt_token=' + client.cookies.get('dt_token')}
        async with websockets.connect(url.replace('http://','ws://')+'/ws', additional_headers=headers,
                                      origin=url, open_timeout=15, max_size=8_000_000) as ws:
            await ws.send(json.dumps({
                'type':'start_turn', 'protocol_version':'2.0', 'client_submission_id':uuid.uuid4().hex,
                'content':question, 'language':'zh', 'session_id':session, 'capability':'immersive_reading',
                'workspace_mode':'reading', 'reading_material_id':mid, 'reading_workspace_id':wid,
            }, ensure_ascii=False))
            content = ''
            while True:
                event = json.loads(await asyncio.wait_for(ws.recv(), timeout=45))
                kind = event.get('type')
                assert kind not in ('error','protocol_error'), event.get('error_code')
                if kind == 'content':
                    content += event.get('content','')
                if kind == 'done':
                    assert '已收到你的教材问题' in content
                    return

    for role in ('business', 'rag'):
        with connect(databases, role, 'src') as db:
            db.execute("CREATE TABLE rehearsal_marker (marker TEXT PRIMARY KEY)")
            db.execute("INSERT INTO rehearsal_marker (marker) VALUES ('checkpoint')")
    with worker(home, databases, 'source-worker.log') as url:
        with httpx.Client(base_url=url, headers=bridge, trust_env=False, timeout=25) as client:
            login(client, owner)
            original_pdf = pdf_digest(client)
            original_identity = client.get('/api/auth/status').json()['user_id']
            saved = client.put('/api/heart/model', json={'model':'review-alpha',
                'base_url':'https://1.1.1.1/v1','api_key':'local-alpha-fixture'})
            assert saved.status_code == 200, saved.status_code
            before = client.get('/api/heart/model').json()
            assert before['configured'] and before['api_key_masked'].endswith('ture')
            set_pref = client.post('/api/heart/memory/preference', json={'text': preference})
            assert set_pref.status_code in (200,201), set_pref.status_code
            response = client.post(f'/api/reading/workspaces/{wid}/sessions',
                json={'title':'恢复演练','active_material_id':mid})
            assert response.status_code == 201, response.status_code
            session_id = response.json()['session']['session_id']
            asyncio.run(turn(client, url, session_id, questions[0]))
            snapshot_session = client.get(f'/api/sessions/{session_id}').json()
            assert questions[0] in json.dumps(snapshot_session, ensure_ascii=False)

    print('SNAPSHOT_SOURCE_STOPPED', flush=True)
    from scripts.provision_review_accounts import _private_directory
    secret_folder=rehearsal/'private-recovery';_private_directory(secret_folder)
    secret_file=secret_folder/'encryption.json'
    secret_file.write_text(json.dumps({'HEART_MODEL_ENCRYPTION_KEY':os.environ.pop('HEART_MODEL_ENCRYPTION_KEY')}),encoding='utf-8')
    print('PRIVATE_RECOVERY_KEY_BACKED_UP',flush=True)

    archive = rehearsal / 'deeptutor-home.tar.gz'
    with tarfile.open(archive, 'w:gz', compresslevel=1) as backup:
        backup.add(home, arcname='worker-home')
    for role in db_roles:
        args, env = pg_args(databases, role, 'src')
        dump = rehearsal / (role+'.dump')
        subprocess.run([str(pg_bin/'pg_dump.exe'), *args, '--format=custom', '--no-owner',
                       '--file', str(dump)], env=env, check=True, capture_output=True)
        assert dump.stat().st_size > 0
    for role in ('business', 'rag'):
        with connect(databases, role, 'src') as db:
            db.execute("INSERT INTO rehearsal_marker (marker) VALUES ('after-checkpoint')")

    restored = rehearsal / 'restored'
    restored.mkdir()
    with tarfile.open(archive, 'r:gz') as backup:
        backup.extractall(restored, filter='data')
    new_home = restored / 'worker-home'
    source_files = {file.relative_to(home) for file in home.rglob('*') if file.is_file()}
    target_files = {file.relative_to(new_home) for file in new_home.rglob('*') if file.is_file()}
    assert source_files == target_files and source_files
    for file in target_files:
        with (home/file).open('rb') as original, (new_home/file).open('rb') as copy:
            assert hashlib.file_digest(original,'sha256').digest() == hashlib.file_digest(copy,'sha256').digest(), file
    print('WORKER_HOME_ARCHIVE_VERIFIED', flush=True)

    with temp_databases('heart_restore_dst') as target:
        for role in db_roles:
            args, env = pg_args(target, role, 'dst')
            dump = rehearsal / (role+'.dump')
            catalog = subprocess.check_output([str(pg_bin/'pg_restore.exe'), '--list', str(dump)])
            existing_vector_comment = rb'(?m)^(\d+; \d+ \d+ COMMENT - EXTENSION vector *\r?)$'
            filtered, skipped = re.subn(existing_vector_comment, rb';\1', catalog)
            assert skipped == 1, role
            toc = rehearsal / (role+'.restore.list')
            toc.write_bytes(filtered)
            checked = subprocess.run([str(pg_bin/'pg_restore.exe'), *args, '--single-transaction',
                '--exit-on-error', '--no-owner', '--use-list', str(toc), str(dump)],
                env=env, text=True, encoding='utf-8', errors='replace', capture_output=True)
            if checked.returncode:
                raise RuntimeError(f'{role} restore failed: {checked.stderr.strip()}')
        for role in ('business', 'rag'):
            with connect(target, role, 'dst') as db:
                assert db.execute('SELECT marker FROM rehearsal_marker').fetchall() == [('checkpoint',)]
        print('THREE_POSTGRES_DUMPS_RESTORED', flush=True)

        os.environ.update(json.loads(secret_file.read_text('utf-8')))
        with worker(new_home, target, 'restored-worker.log') as url:
            with httpx.Client(base_url=url, headers=bridge, trust_env=False, timeout=25) as client, \
                    httpx.Client(base_url=url, headers=bridge, trust_env=False, timeout=20) as second:
                login(client, owner)
                login(second, other)
                assert client.get('/api/auth/status').json()['user_id'] == original_identity
                assert len(client.get('/api/reading/materials').json()) == 11
                assert pdf_digest(client) == original_pdf
                assert client.get('/api/heart/model').json() == before
                assert second.get('/api/heart/model').json() == {'configured':False}
                assert second.get(f'/api/reading/workspaces/{wid}').status_code == 404
                assert preference in json.dumps(client.get('/api/heart/memory').json(), ensure_ascii=False)
                assert preference not in json.dumps(second.get('/api/heart/memory').json(), ensure_ascii=False)
                replay = client.get(f'/api/sessions/{session_id}').json()
                assert questions[0] in json.dumps(replay, ensure_ascii=False)
                asyncio.run(turn(client, url, session_id, questions[1]))
                continued = json.dumps(client.get(f'/api/sessions/{session_id}').json(), ensure_ascii=False)
                assert all(question in continued for question in questions)
        for role in ('business', 'rag'):
            with connect(databases, role, 'src') as db:
                assert db.execute("SELECT marker FROM rehearsal_marker ORDER BY marker").fetchall() == [
                    ('after-checkpoint',), ('checkpoint',)]
        print('RESTORED_RUNTIME_RESUMED_TURN_AND_SOURCE_INTACT', flush=True)

    (RUN/'task10-restore-results.json').write_text(json.dumps({'worker_home_verified':True,'three_postgres_dumps_restored':True,'private_encryption_key_backed_up_and_reloaded':True,'same_auth_identity':True,'model_decryption':True,'textbook_pdf_unchanged':True,'restored_turn_continued':True,'source_post_checkpoint_records_preserved':True,'temporary_databases_only':True},indent=2),encoding='utf-8')
