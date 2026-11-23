"""学生截图按上传时间保留 30 天；仅未完成识别可延长，绝不超过 60 天。"""
from __future__ import annotations
import asyncio,json,mimetypes,time
from contextlib import asynccontextmanager,suppress
from hashlib import sha256
from pathlib import Path
DAY=86400

def actor():
    from deeptutor.multi_user.context import get_current_user_or_none
    user=get_current_user_or_none()
    return user if user and not user.is_admin else None

def manifest(store,session,attachment):
    # 文件名使用哈希，不让客户端 ID 成为路径组件。
    return store._session_dir(session)/('.heart-image-'+sha256(attachment.encode()).hexdigest()+'.json')

def load(path):
    return json.loads(path.read_text('utf-8'))

def save(path,row):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(row,ensure_ascii=False),'utf-8');tmp.replace(path)

def dependencies(session,attachment):
    from deeptutor.services.session import get_sqlite_session_store
    store=get_sqlite_session_store()
    with store._connect() as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='heart_screenshot_inputs'").fetchone():return []
        rows=conn.execute("SELECT i.turn_id,i.result_json FROM heart_screenshot_inputs i JOIN turns t ON t.id=i.turn_id WHERE i.session_id=? AND i.status='sent' AND t.status IN ('queued','running','waiting_input')",(session,)).fetchall()
    return [row['turn_id'] for row in rows if attachment in json.loads(row['result_json']).get('attachment_ids',[])]

class Policy:
    def uploaded(self,store,session,attachment,filename,data,mime):
        user=actor()
        if not user or not (mime or mimetypes.guess_type(filename)[0] or '').startswith('image/'):return
        path=manifest(store,session,attachment)
        digest=sha256(data).hexdigest()
        if path.exists():
            row=load(path)
            if (row['owner'],row['vendor_id'],row['sha256'])!=(user.username,user.id,digest):raise ValueError('screenshot_identity_changed')
            self.check(store,session,attachment,filename)
            return  # 重放不能重置原上传时间。
        save(path,{'owner':user.username,'vendor_id':user.id,'session_id':session,'attachment_id':attachment,
            'stored_name':store._stored_filename(attachment,filename),'uploaded_at':time.time(),'sha256':digest,'expired':False})
    def check(self,store,session,attachment,filename):
        from deeptutor.services.storage.attachment_store import AttachmentExpiredError
        user=actor()
        if not user:return
        path=manifest(store,session,attachment)
        if not path.exists():
            if (mimetypes.guess_type(filename)[0] or '').startswith('image/'):raise AttachmentExpiredError('untracked_student_image')
            return
        row=load(path)
        if (row['owner'],row['vendor_id'])!=(user.username,user.id):raise AttachmentExpiredError('screenshot_identity_changed')
        age=time.time()-row['uploaded_at']
        if row['expired'] or age>=60*DAY or (age>=30*DAY and not dependencies(session,attachment)):
            raise AttachmentExpiredError('screenshot_expired')
    def delete_session(self,store,session):
        user=actor()
        if not user:return False
        directory=store._session_dir(session)
        if not directory.exists():return True
        for path in directory.glob('.heart-image-*.json'):
            row=load(path)
            if (row['owner'],row['vendor_id'])!=(user.username,user.id):continue
            if time.time()-row['uploaded_at']<60*DAY and dependencies(session,row['attachment_id']):continue
            self.expire(store,path,row)
        # 清除会话中的其他附件；已过期截图仅留无原文的期限标记。
        protected={load(p)['stored_name'] for p in directory.glob('.heart-image-*.json') if not load(p)['expired']}
        for path in directory.iterdir():
            if path.is_file() and not path.name.startswith('.heart-image-') and path.name not in protected:
                if path.resolve().is_relative_to(store.root.resolve()):path.unlink()
        return True
    def expire(self,store,path,row):
        target=path.parent/row['stored_name']
        if target.name!=row['stored_name'] or not target.resolve().is_relative_to(store.root.resolve()):raise ValueError('unsafe_attachment_path')
        if target.is_file():target.unlink()
        row['expired']=True;save(path,row)
    def prune(self,store):
        user=actor()
        if not user or not store.root.exists():return []
        cancel=[]
        for path in store.root.glob('*/.heart-image-*.json'):
            if not path.resolve().is_relative_to(store.root.resolve()):continue
            row=load(path)
            if row['expired'] or (row['owner'],row['vendor_id'])!=(user.username,user.id):continue
            age=time.time()-row['uploaded_at']
            if age<30*DAY:continue
            pending=dependencies(row['session_id'],row['attachment_id'])
            if age<60*DAY and pending:continue
            if pending:
                from deeptutor.services.session import get_sqlite_session_store
                with get_sqlite_session_store()._connect() as conn:
                    for turn in pending:
                        conn.execute("UPDATE heart_screenshot_inputs SET status='expired',result_json=? WHERE turn_id=? AND status='sent'",
                            (json.dumps({'message':'原图已达到 60 天保留上限，本次任务已停止，不评分。'},ensure_ascii=False),turn))
                cancel.extend(pending)
            self.expire(store,path,row)
        return cancel

policy=Policy()

async def sweep():
    from deeptutor.services.auth import list_users
    from deeptutor.multi_user.models import CurrentUser
    from deeptutor.multi_user.paths import scope_for_user,user_context
    from deeptutor.services.workspace import get_content_workspace_service
    from deeptutor.services.workspace.context import workspace_context
    from deeptutor.services.storage import get_attachment_store
    from deeptutor.api.routers.sessions import _turn_application_service
    for account in list_users():
        if account.get('disabled') or account.get('role')=='admin' or not account.get('id'):continue
        user=CurrentUser(id=account['id'],username=account['username'],role='student',scope=scope_for_user(account['id'],is_admin=False))
        with user_context(user):
            scopes=['']+[r['workspace_id'] for r in get_content_workspace_service().list_workspaces() if r['kind']=='workspace']
            for workspace in scopes:
                with workspace_context(workspace):
                    for turn in await asyncio.to_thread(policy.prune,get_attachment_store()):
                        await _turn_application_service().cancel_turn_and_wait(turn)

def install(app):
    from deeptutor.services.storage.attachment_store import set_external_attachment_policy
    set_external_attachment_policy(policy)
    previous=app.router.lifespan_context
    async def loop():
        import logging
        while True:
            try:await sweep()
            except Exception:logging.getLogger(__name__).warning('截图期限检查等待恢复')
            await asyncio.sleep(60)
    @asynccontextmanager
    async def lifespan(application):
        async with previous(application) as state:
            task=asyncio.create_task(loop())
            try:yield state
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):await task
    app.router.lifespan_context=lifespan
