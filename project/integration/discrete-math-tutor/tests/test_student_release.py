"""发行快照、切换并发门禁及回退不触碰新数据。"""
import json,sqlite3
from pathlib import Path
import pytest
from deploy.student_release import bundle,inspect,verify,select,HROOT,VROOT

def test_release_roundtrip_keeps_new_records_and_rejects_tampering(tmp_path):
 source=tmp_path/"source"
 for root in (HROOT,VROOT):
  (source/root).mkdir(parents=True);(source/root/"main.py").write_text("version=1")
 (source/HROOT/".env").write_text("PRIVATE=not-for-release")
 (source/HROOT/"data").mkdir();(source/HROOT/"data/private.txt").write_text("private")
 deploy=tmp_path/"deployment";old=deploy/"releases/old";new=deploy/"releases/new"
 bundle(source,old,"old");(source/HROOT/"main.py").write_text("version=2");bundle(source,new,"new")
 assert not (old/HROOT/".env").exists() and not (old/HROOT/"data").exists()
 state=deploy/"student.sqlite"
 with sqlite3.connect(state) as db:db.execute("CREATE TABLE evidence(value TEXT)");db.execute("INSERT INTO evidence VALUES ('before-switch')")
 select(deploy,old,None);select(deploy,new,"old")
 with sqlite3.connect(state) as db:db.execute("INSERT INTO evidence VALUES ('new-student-evidence')")
 select(deploy,old,"new");select(deploy,new,"old")
 with sqlite3.connect(state) as db:assert db.execute("SELECT value FROM evidence").fetchall()==[("before-switch",),("new-student-evidence",)]
 with pytest.raises(ValueError,match="current_release_changed"):select(deploy,old,"old")
 (new/HROOT/"main.py").write_text("tampered")
 with pytest.raises(ValueError,match="release_hash_mismatch"):verify(new)


def test_release_rejects_unlisted_code_and_wrong_destination(tmp_path):
 source=tmp_path/"source"
 for root in (HROOT,VROOT):
  (source/root).mkdir(parents=True);(source/root/"main.py").write_text("safe")
 output=tmp_path/"release";bundle(source,output,"candidate")
 (output/HROOT/"injected.py").write_text("unlisted")
 with pytest.raises(ValueError,match="release_file_inventory_changed"):verify(output)
 with pytest.raises(ValueError,match="output_inside_source"):bundle(source,source/HROOT/"output","bad")


def test_switch_uses_inventory_without_rehashing_release_files(tmp_path):
 source=tmp_path/"source"
 for root in (HROOT,VROOT):
  (source/root).mkdir(parents=True);(source/root/"main.py").write_text("version=1")
 deploy=tmp_path/"deployment";old=deploy/"releases/old";new=deploy/"releases/new"
 bundle(source,old,"old");bundle(source,new,"new");select(deploy,old,None)
 (new/HROOT/"main.py").write_text("tampered")
 assert inspect(new)["release_id"]=="new"
 with pytest.raises(ValueError,match="release_hash_mismatch"):verify(new)
 # 切换只核对清单与路径；完整哈希校验留给显式 verify 命令。
 select(deploy,new,"old")
 (new/HROOT/"injected.py").write_text("unlisted")
 with pytest.raises(ValueError,match="release_file_inventory_changed"):inspect(new)


def test_runtime_plan_keeps_secrets_out_of_frontend_and_rejects_missing_build(tmp_path,monkeypatch):
 import importlib.util,sys,os
 deploy_path=Path(__file__).resolve().parents[1]/"deploy"
 monkeypatch.syspath_prepend(str(deploy_path))
 from run_student_release import plan
 import run_student_release
 monkeypatch.setattr(run_student_release,"verify",
  lambda *a,**k:(_ for _ in ()).throw(AssertionError("runtime plan rehashed release")),raising=False)
 source=tmp_path/"source"
 for root in (HROOT,VROOT):
  (source/root).mkdir(parents=True);(source/root/"main.py").write_text("safe")
 root=tmp_path/"deploy";release=root/"releases/current";bundle(source,release,"current");select(root,release,None)
 env={"DEEPTUTOR_HOME":str(tmp_path/"home"),"TUTOR_PSYCHOLOGY_DIR":str(tmp_path/"assets"),"COURSE_DATABASE_URL":"private-course","DATABASE_URL":"private-main","POSTGRES_HOST":"private-host","POSTGRES_DATABASE":"private-rag","HEART_MODEL_ENCRYPTION_KEY":"private-encryption","DEEPTUTOR_BRIDGE_TOKEN":"b"*40,"DEEPSEEK_API_KEY":"private-model"}
 home=Path(env["DEEPTUTOR_HOME"]);(home/"data/user/settings").mkdir(parents=True);(home/"data/system/auth").mkdir(parents=True)
 (home/"data/user/settings/auth.json").write_text('{"enabled":true}')
 (home/"data/system/auth/users.json").write_text('{"admin":{"role":"admin"}}')
 (home/"data/system/auth/auth_secret").write_text("private-secret")
 with pytest.raises(ValueError,match="target_web_build_missing"):plan(root,"web",env)
 node=tmp_path/"node";node.touch();env["HEART_RUNTIME_NODE"]=str(node)
 web=release/VROOT/"web/.next/standalone";(web/".next/static").mkdir(parents=True);(web/"server.js").write_text("runtime")
 command,cwd,front=plan(root,"web",env)
 assert command==[str(node),"server.js"] and front["HOSTNAME"]=="127.0.0.1"
 assert all(key not in front for key in ("DATABASE_URL","MEMORY_DATABASE_URL","HEART_MODEL_ENCRYPTION_KEY","DEEPSEEK_API_KEY"))
 assert front["DEEPTUTOR_BRIDGE_TOKEN"]=="b"*40

 env.update(HEART_HOST_PORT="18000",HEART_WEB_PORT="8000")
 _,_,local=plan(root,"web",env)
 assert local["PORT"]=="8000" and local["HEART_API_BASE_URL"]=="http://127.0.0.1:18000"
 env["HEART_WORKER_PORT"]="8000"
 with pytest.raises(ValueError,match="invalid_service_ports"):plan(root,"web",env)
 env["HEART_WORKER_PORT"]="18001"

 env["DEEPTUTOR_HOME"]=str(release/"data")
 with pytest.raises(ValueError,match="mutable_resource_inside_release"):plan(root,"web",env)


def test_local_setup_selects_cuda_rerank_only_when_target_python_has_it(tmp_path):
 from deploy.setup_student_local import rerank_device
 from types import SimpleNamespace
 ok=lambda *a,**k:SimpleNamespace(returncode=0,stdout="1\n")
 cpu=lambda *a,**k:SimpleNamespace(returncode=0,stdout="0\n")
 def missing(*a,**k):raise OSError("python missing")
 python=tmp_path/"python.exe"
 assert rerank_device(python,run=ok)=="cuda"
 assert rerank_device(python,run=cpu)=="cpu"
 assert rerank_device(python,run=missing)=="cpu"


def test_release_ignores_runtime_jit_cache(tmp_path):
 source=tmp_path/"source"
 for root in (HROOT,VROOT):
  (source/root).mkdir(parents=True);(source/root/"main.py").write_text("safe")
 output=tmp_path/"release";bundle(source,output,"candidate")
 cache=output/HROOT/".cache/cuda";cache.mkdir(parents=True);(cache/"jit.bin").write_bytes(b"jit")
 # CUDA JIT 缓存写在发行目录内不能把下次启动判成发行被改动。
 assert inspect(output)["release_id"]=="candidate"
 verify(output)


def test_inspect_names_a_deleted_release_file(tmp_path):
 source=tmp_path/"source"
 for root in (HROOT,VROOT):
  (source/root).mkdir(parents=True);(source/root/"main.py").write_text("safe")
 output=tmp_path/"release";bundle(source,output,"candidate")
 (output/HROOT/"main.py").unlink()
 with pytest.raises(ValueError,match="release_file_missing:"+HROOT.as_posix()+"/main.py"):
  inspect(output)


def test_runtime_plan_can_pin_one_release_for_all_services(tmp_path,monkeypatch):
 source=tmp_path/"source"
 for root in (HROOT,VROOT):
  (source/root).mkdir(parents=True);(source/root/"main.py").write_text("one")
 root=tmp_path/"deploy";old=root/"releases/old";new=root/"releases/new"
 bundle(source,old,"old");(source/HROOT/"main.py").write_text("two");bundle(source,new,"new")
 select(root,old,None)
 monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/"deploy"))
 from run_student_release import active_release,plan
 env={"DEEPTUTOR_HOME":str(tmp_path/"home"),"TUTOR_PSYCHOLOGY_DIR":str(tmp_path/"assets"),"COURSE_DATABASE_URL":"c","DATABASE_URL":"m","POSTGRES_HOST":"h","POSTGRES_DATABASE":"r","HEART_MODEL_ENCRYPTION_KEY":"e","DEEPTUTOR_BRIDGE_TOKEN":"b"*40}
 home=Path(env["DEEPTUTOR_HOME"]);(home/"data/user/settings").mkdir(parents=True);(home/"data/system/auth").mkdir(parents=True)
 (home/"data/user/settings/auth.json").write_text('{"enabled":true}')
 (home/"data/system/auth/users.json").write_text('{"admin":{"role":"admin"}}')
 (home/"data/system/auth/auth_secret").write_text("secret")
 node=tmp_path/"node";node.touch();env["HEART_RUNTIME_NODE"]=str(node)
 web=old/VROOT/"web/.next/standalone";(web/".next/static").mkdir(parents=True);(web/"server.js").write_text("runtime")
 pinned=active_release(root)
 select(root,new,"old")
 # 三个服务在同一次启动里必须用同一个已解析发行，不受并发选版影响。
 _,cwd,_=plan(root,"web",env,active=pinned)
 assert Path(cwd)==web


def test_registered_service_on_another_release_is_not_reused(monkeypatch):
 from deploy import manage_student_local as manage
 monkeypatch.setattr(manage,"matching",lambda row:object())
 records={"worker":{"release_id":"a"},"host":{"release_id":"a"}}
 assert manage.pending_services(records,"a")==["web"]
 with pytest.raises(RuntimeError,match="service_on_other_release:worker"):
  manage.pending_services(records,"b")


def test_local_setup_pins_cuda_jit_cache_outside_release(tmp_path):
 from deploy.setup_student_local import rerank_settings
 from types import SimpleNamespace
 private=tmp_path/"private";python=tmp_path/"python.exe"
 cuda=lambda *a,**k:SimpleNamespace(returncode=0,stdout="1\n")
 cpu=lambda *a,**k:SimpleNamespace(returncode=0,stdout="0\n")
 assert rerank_settings(private,python,run=cuda)=={
  "RAG_RERANK_DEVICE":"cuda","CUDA_CACHE_PATH":str(private/"cuda-cache")}
 assert rerank_settings(private,python,run=cpu)=={"RAG_RERANK_DEVICE":"cpu"}


def test_knowledge_python_and_release_metadata_are_code_but_course_assets_stay_external(tmp_path):
 source=tmp_path/"source"
 for root in (HROOT,VROOT):(source/root).mkdir(parents=True)
 folder=source/HROOT/"knowledge";folder.mkdir();(folder/"__init__.py").write_text("code");(folder/"graph_release.json").write_text("{}")
 (folder/"courses/book").mkdir(parents=True);(folder/"courses/book/private.pdf").write_bytes(b"asset")
 output=tmp_path/"release";bundle(source,output,"candidate")
 assert (output/HROOT/"knowledge/__init__.py").is_file() and (output/HROOT/"knowledge/graph_release.json").is_file()
 assert not (output/HROOT/"knowledge/courses").exists()
