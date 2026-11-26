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


def test_knowledge_python_and_release_metadata_are_code_but_course_assets_stay_external(tmp_path):
 source=tmp_path/"source"
 for root in (HROOT,VROOT):(source/root).mkdir(parents=True)
 folder=source/HROOT/"knowledge";folder.mkdir();(folder/"__init__.py").write_text("code");(folder/"graph_release.json").write_text("{}")
 (folder/"courses/book").mkdir(parents=True);(folder/"courses/book/private.pdf").write_bytes(b"asset")
 output=tmp_path/"release";bundle(source,output,"candidate")
 assert (output/HROOT/"knowledge/__init__.py").is_file() and (output/HROOT/"knowledge/graph_release.json").is_file()
 assert not (output/HROOT/"knowledge/courses").exists()
