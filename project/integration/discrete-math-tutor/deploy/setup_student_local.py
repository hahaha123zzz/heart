"""为已授权的本机 8000 测试初始化独立永久存储；不清理现有数据。"""
from __future__ import annotations
import argparse,json,os,secrets,subprocess,sys,hashlib
from pathlib import Path
from urllib.parse import urlsplit

def rerank_settings(private, python, *, run=subprocess.run):
 """新装重排配置；CUDA 时把 ONNX JIT 缓存固定在部署私有目录，避免写进发行包。"""
 device=rerank_device(python,run=run)
 settings={"RAG_RERANK_DEVICE":device}
 if device=="cuda":settings["CUDA_CACHE_PATH"]=str(Path(private)/"cuda-cache")
 return settings

def rerank_device(python, *, run=subprocess.run):
 """新装只在本机目标解释器能启用 CUDA 时才把正式教材重排切到 GPU。"""
 try:
  probe=run([str(python),"-c","import onnxruntime as o;print(int('CUDAExecutionProvider' in o.get_available_providers()))"],
            capture_output=True,text=True,timeout=120,check=False)
 except (OSError,subprocess.SubprocessError):
  return "cpu"
 return "cuda" if probe.returncode==0 and probe.stdout.strip()=="1" else "cpu"

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--root",type=Path,required=True);parser.add_argument("--project-env",type=Path,required=True);parser.add_argument("--assets",type=Path,required=True);parser.add_argument("--python",type=Path,required=True);parser.add_argument("--node",type=Path,required=True);parser.add_argument("--extra-path",action="append",default=[]);parser.add_argument("--early-path",action="append",default=[]);args=parser.parse_args()
 host=Path(__file__).resolve().parents[1];vendor=host.parents[1]/"vendor/DeepTutor";sys.path[:0]=[str(host),str(vendor),*args.early_path];sys.path.extend(args.extra_path)
 from dotenv import dotenv_values
 from cryptography.fernet import Fernet
 from scripts.provision_review_accounts import _private_directory,provision,NAMES
 root=args.root.resolve();root.mkdir(parents=True,exist_ok=True);private=root/"private";_private_directory(private)
 config=private/"runtime.env";marker=private/"local-setup.json"
 if config.exists()!=marker.exists():raise ValueError("incomplete_local_setup_requires_review")
 if not config.exists():
  import psycopg
  from psycopg import sql
  project={k:v for k,v in dotenv_values(args.project_env).items() if isinstance(v,str)};os.environ.update(project)
  from tests.pg_support import maintenance_url,_psycopg_url,_ensure_extensions
  suffix=hashlib.sha256(str(root).encode()).hexdigest()[:10];names=["heart_local8000_"+suffix,"heart_local8000_course_"+suffix]
  base=maintenance_url()
  with psycopg.connect(base,autocommit=True) as connection:
   for name in names:
    if connection.execute("SELECT 1 FROM pg_database WHERE datname=%s",(name,)).fetchone():raise ValueError("unowned_local_database_exists")
   for name in names:connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
  _ensure_extensions(names)
  rerank=rerank_settings(private,args.python)
  values={**project,"DATABASE_URL":_psycopg_url(urlsplit(base),names[0]).replace("postgresql://","postgresql+psycopg://",1),"COURSE_DATABASE_URL":_psycopg_url(urlsplit(base),names[1]).replace("postgresql://","postgresql+psycopg://",1),"DEEPTUTOR_HOME":str(private/"worker-home"),"TUTOR_PSYCHOLOGY_DIR":str(args.assets.resolve(strict=True)),"HEART_MODEL_ENCRYPTION_KEY":Fernet.generate_key().decode(),"DEEPTUTOR_BRIDGE_TOKEN":secrets.token_urlsafe(40),"HEART_HOST_PORT":"18000","HEART_WORKER_PORT":"18001","HEART_WEB_PORT":"8000","HEART_RUNTIME_PYTHON":str(args.python.resolve(strict=True)),"HEART_RUNTIME_NODE":str(args.node.resolve(strict=True)),"HEART_RUNTIME_EXTRA_PATHS":os.pathsep.join(args.extra_path),"AUTH_ENABLED":"true","NEXT_PUBLIC_AUTH_ENABLED":"true","DEEPTUTOR_AUTH_ENABLED":"true","AUTH_USERNAME":"","AUTH_PASSWORD_HASH":"","POCKETBASE_URL":"","DEEPTUTOR_NATIVE_ENABLED":"1","DEEPTUTOR_AUTOSTART":"0","CLEANUP_EXPIRED_ON_STARTUP":"0","RAG_EMBED_DEVICE":"cpu",**rerank,"MEM0_ENABLED":"1","MEM0_HISTORY_PATH":str(private/"worker-home/.runtime/mem0/history.sqlite")}
  config.write_text("".join(k+"="+json.dumps(v,ensure_ascii=False)+"\n" for k,v in sorted(values.items())),encoding="utf-8")
  marker.write_text(json.dumps({"kind":"local8000","databases":names,"home":values["DEEPTUTOR_HOME"],"rerank":rerank},indent=2),encoding="utf-8")
 values={k:v for k,v in dotenv_values(config).items() if isinstance(v,str)}
 values.update(HEART_RUNTIME_EARLY_PATHS=os.pathsep.join(args.early_path),HEART_RUNTIME_EXTRA_PATHS=os.pathsep.join(args.extra_path),HEART_RUNTIME_PYTHON=str(args.python.resolve(strict=True)),HEART_RUNTIME_NODE=str(args.node.resolve(strict=True)))
 config.write_text("".join(k+"="+json.dumps(v,ensure_ascii=False)+"\n" for k,v in sorted(values.items())),encoding="utf-8")
 os.environ.update(values)
 home=Path(values["DEEPTUTOR_HOME"]);settings=home/"data/user/settings";settings.mkdir(parents=True,exist_ok=True)
 auth_file=settings/"auth.json"
 if not auth_file.exists():auth_file.write_text('{"enabled":true}',encoding="utf-8")
 from database.database import engine
 from database.models import Base
 expected=json.loads(marker.read_text("utf-8"))["databases"]
 if engine.url.database!=expected[1]:raise ValueError("wrong_local_database")
 Base.metadata.create_all(engine)
 from deeptutor.services import auth
 admin=private/"admin-account.txt"
 if not auth.get_user_info("heart-local-admin"):
  password=secrets.token_urlsafe(32);admin.write_text("heart-local-admin\t"+password+"\n",encoding="utf-8");auth.add_user("heart-local-admin",password,role="admin")
 created,credential_file=provision(home)
 from scripts.assign_review_reading import assign
 readings=assign(home,args.assets.resolve(strict=True))
 from database.repository import Repository
 repo=Repository()
 for name in NAMES:repo.ensure_student(name)
 result={"local_url":"http://127.0.0.1:8000","accounts":len(NAMES),"new_accounts":created,"chapters_per_account":len(next(iter(readings.values()))["materials"]),"credential_file":str(credential_file),"persistent_home":str(home),"databases":expected,"no_old_data_migrated":True}
 (private/"local-ready.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
 print(json.dumps({k:result[k] for k in ("local_url","accounts","new_accounts","chapters_per_account","credential_file")}))
if __name__=="__main__":main()
