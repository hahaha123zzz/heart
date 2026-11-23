"""图片期限仅使用临时路径及受控时间；不调用模型。"""
import asyncio,json
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

@pytest.fixture
def assets(tmp_path,monkeypatch):
 from integrations.deeptutor import attachment_retention as r
 from deeptutor.services.storage.attachment_store import LocalDiskAttachmentStore
 user=SimpleNamespace(username='owner',id='vendor')
 monkeypatch.setattr(r,'actor',lambda:user)
 monkeypatch.setattr(r,'dependencies',lambda *args:[])
 clock=[100*r.DAY];monkeypatch.setattr(r.time,'time',lambda:clock[0])
 store=LocalDiskAttachmentStore(tmp_path/'assets');store.root.mkdir()
 def upload():
  r.policy.uploaded(store,'s','a','question.png',b'image','image/png')
  target=store._safe_join('s',store._stored_filename('a','question.png'))
  target.write_bytes(b'image');return target
 target=upload()
 return SimpleNamespace(r=r,user=user,store=store,clock=clock,target=target,upload=upload)

def test_normal_expiry_removes_bytes_but_preserves_original_time_and_marker(assets):
 a=assets;r=a.r
 a.clock[0]+=29*r.DAY;a.upload()
 assert r.load(r.manifest(a.store,'s','a'))['uploaded_at']==100*r.DAY
 a.clock[0]+=r.DAY
 assert r.policy.prune(a.store)==[]
 assert not a.target.exists()
 from deeptutor.services.storage.attachment_store import AttachmentExpiredError
 with pytest.raises(AttachmentExpiredError):r.policy.check(a.store,'s','a','question.png')
 assert r.load(r.manifest(a.store,'s','a'))['expired']

def test_pending_original_extends_only_to_hard_cap_and_late_result_is_rejected(assets,monkeypatch,tmp_path):
 a=assets;r=a.r
 from deeptutor.services.session.sqlite_store import SQLiteSessionStore
 from deeptutor.services import session
 from integrations.deeptutor import screenshot_intake as intake
 native=SQLiteSessionStore(tmp_path/'session.db');monkeypatch.setattr(session,'get_sqlite_session_store',lambda:native)
 with intake._connect(native.db_path) as conn:
  conn.execute("INSERT INTO heart_screenshot_inputs VALUES('turn','owner','vendor','s','hash','model','version','sent',?,0)",(json.dumps({'attachment_ids':['a']}),))
 monkeypatch.setattr(r,'dependencies',lambda *args:['turn'])
 a.clock[0]+=40*r.DAY
 assert r.policy.prune(a.store)==[] and a.target.exists()
 assert r.policy.delete_session(a.store,'s') and a.target.exists()
 a.clock[0]=160*r.DAY
 assert r.policy.prune(a.store)==['turn'] and not a.target.exists()
 assert intake._finish(native.db_path,'turn','completed',{'late':'result'}) is False

def test_finished_dependency_cleans_immediately_after_extended_period(assets,monkeypatch):
 a=assets;r=a.r;a.clock[0]+=40*r.DAY
 monkeypatch.setattr(r,'dependencies',lambda *args:['pending'])
 assert not r.policy.prune(a.store) and a.target.exists()
 monkeypatch.setattr(r,'dependencies',lambda *args:[])
 r.policy.prune(a.store);assert not a.target.exists()

def test_owner_rebinding_and_changed_image_cannot_reset_upload_age(assets):
 a=assets;r=a.r
 with pytest.raises(ValueError):r.policy.uploaded(a.store,'s','a','question.png',b'changed','image/png')
 a.user.id='different'
 from deeptutor.services.storage.attachment_store import AttachmentExpiredError
 with pytest.raises(AttachmentExpiredError):r.policy.check(a.store,'s','a','question.png')


def test_only_live_native_turns_can_extend_original_image_retention(tmp_path,monkeypatch):
 from integrations.deeptutor import attachment_retention as r,screenshot_intake as intake
 from deeptutor.services.session.sqlite_store import SQLiteSessionStore
 from deeptutor.services import session
 native=SQLiteSessionStore(tmp_path/'dependencies.db')
 asyncio.run(native.create_session(session_id='s'))
 with native._connect() as conn:
  conn.execute("INSERT INTO turns(id,session_id,status,created_at,updated_at) VALUES('turn','s','running',0,0)")
 with intake._connect(native.db_path) as conn:
  conn.execute("INSERT INTO heart_screenshot_inputs VALUES('turn','owner','vendor','s','hash','model','version','sent',?,0)",(json.dumps({'attachment_ids':['image']}),))
 monkeypatch.setattr(session,'get_sqlite_session_store',lambda:native)
 assert r.dependencies('s','image')==['turn']
 with native._connect() as conn:conn.execute("UPDATE turns SET status='failed' WHERE id='turn'")
 assert r.dependencies('s','image')==[]
