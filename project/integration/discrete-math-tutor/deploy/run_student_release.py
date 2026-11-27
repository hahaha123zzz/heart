"""从受控发行选择启动一种服务；--check 只核验，--run 才替换当前进程。"""
from __future__ import annotations
import argparse,json,os,sys,time
from pathlib import Path
from dotenv import dotenv_values
try:
 from .student_release import inspect,HROOT,VROOT
except ImportError:
 from student_release import inspect,HROOT,VROOT

def active_release(root:Path):
 """一次启动只解析一次发行指针；三个服务共用同一份已解析结果。"""
 root=root.resolve(strict=True);active=json.loads((root/"active-release.json").read_text("utf-8"))
 if not isinstance(active.get("release_id"),str):raise ValueError("invalid_active_release")
 release=Path(active["release_path"]).resolve(strict=True)
 if not release.is_relative_to(root/"releases"):raise ValueError("invalid_active_release")
 return active,release

def plan(root:Path,service:str,values:dict,timing:dict|None=None,active=None):
 root=root.resolve(strict=True)
 if active is None:active,release=active_release(root)
 else:active,release=active
 if not release.is_relative_to(root/"releases"):raise ValueError("invalid_active_release")
 began=time.perf_counter()
 manifest=inspect(release)
 if timing is not None:timing.update(release_seconds=time.perf_counter()-began,
  file_count=len(manifest["files"]),release_id=manifest["release_id"],service=service)
 if manifest["release_id"]!=active["release_id"]:raise ValueError("active_identity_mismatch")
 env={**os.environ,**{k:v for k,v in values.items() if isinstance(v,str)}}
 for key in ("DEEPTUTOR_HOME","TUTOR_PSYCHOLOGY_DIR","COURSE_DATABASE_URL","DATABASE_URL","POSTGRES_HOST","POSTGRES_DATABASE","HEART_MODEL_ENCRYPTION_KEY","DEEPTUTOR_BRIDGE_TOKEN"):
  if not env.get(key):raise ValueError("missing_runtime_setting:"+key)
 for key in ("DEEPTUTOR_HOME","TUTOR_PSYCHOLOGY_DIR"):
  value=Path(env[key])
  if not value.is_absolute() or value.resolve().is_relative_to(root/"releases"):raise ValueError("mutable_resource_inside_release:"+key)
 home=Path(env["DEEPTUTOR_HOME"])
 auth=home/"data/user/settings/auth.json";users=home/"data/system/auth/users.json";secret=home/"data/system/auth/auth_secret"
 if not auth.is_file() or json.loads(auth.read_text("utf-8")).get("enabled") is not True or not users.is_file() or not json.loads(users.read_text("utf-8")) or not secret.is_file():raise ValueError("local_auth_not_provisioned")
 env.update(AUTH_ENABLED="true",NEXT_PUBLIC_AUTH_ENABLED="true",DEEPTUTOR_AUTH_ENABLED="true",AUTH_USERNAME="",AUTH_PASSWORD_HASH="",POCKETBASE_URL="",MEM0_HISTORY_PATH=str(home/".runtime/mem0/history.sqlite"))
 if len(env["DEEPTUTOR_BRIDGE_TOKEN"])<32:raise ValueError("bridge_token_too_short")
 ports=[int(env.get(key,default)) for key,default in (("HEART_HOST_PORT","8000"),("HEART_WORKER_PORT","18001"),("HEART_WEB_PORT","3782"))]
 if len(set(ports))!=3 or any(not 1<=port<=65535 for port in ports):raise ValueError("invalid_service_ports")
 host_port,worker_port,web_port=map(str,ports)
 host_url="http://127.0.0.1:"+host_port;worker_url="http://127.0.0.1:"+worker_port
 single=values.get("HEART_SINGLE_BACKEND")=="1"
 host=release/HROOT;vendor=release/VROOT
 env.update(DEEPTUTOR_NATIVE_ENABLED="1",DEEPTUTOR_AUTOSTART="0",CLEANUP_EXPIRED_ON_STARTUP="0",DEEPTUTOR_BACKEND_URL=(host_url if single else worker_url),DEEPTUTOR_HOST_URL=host_url)
 env["PYTHONPATH"]=os.pathsep.join([str(host),str(vendor),*filter(None,env.get("HEART_RUNTIME_EARLY_PATHS","").split(os.pathsep))])
 python=Path(env["HEART_RUNTIME_PYTHON"]) if env.get("HEART_RUNTIME_PYTHON") else root/"environments"/manifest["release_id"]/("Scripts/python.exe" if os.name=="nt" else "bin/python")
 if service in {"host","worker"}:
  if not python.is_file():raise ValueError("target_python_environment_missing")
  if service=="host":
   args=["uvicorn","main:app","--host","127.0.0.1","--port",host_port]
   entry="runpy.run_module('uvicorn',run_name='__main__')"
  else:
   args=[str(host/"integrations/deeptutor/worker.py"),"--home",env["DEEPTUTOR_HOME"],"--port",worker_port]
   entry="runpy.run_path(sys.argv[0],run_name='__main__')"
  bootstrap="import os,sys,runpy;sys.path.extend(filter(None,os.environ.get('HEART_RUNTIME_EXTRA_PATHS','').split(os.pathsep)));sys.argv="+repr(args)+";"+entry
  cmd=[str(python),"-c",bootstrap]
  return cmd,home,env
 if service!="web":raise ValueError("invalid_service")
 node=Path(env.get("HEART_RUNTIME_NODE",""));web=vendor/"web/.next/standalone"
 if not node.is_absolute() or not node.is_file() or not (web/"server.js").is_file() or not (web/".next/static").is_dir():raise ValueError("target_web_build_missing")
 # 网页进程只拿代理与鉴权所需配置，不继承 PG、加密密钥和项目模型 Key。
 keep={"PATH","SYSTEMROOT","TEMP","TMP","HOME","LANG","NODE_EXTRA_CA_CERTS"}
 front={key:value for key,value in env.items() if key in keep or key.startswith(("HEART_PRIVATE_LOGIN_","DEEPTUTOR_AUTH_"))}
 front.update(PORT=web_port,HOSTNAME="127.0.0.1",NODE_ENV="production",DEEPTUTOR_API_BASE_URL=(host_url if single else worker_url),DEEPTUTOR_BACKEND_URL=(host_url if single else worker_url),HEART_API_BASE_URL=host_url,DEEPTUTOR_HOST_URL=host_url,DEEPTUTOR_BRIDGE_TOKEN=env["DEEPTUTOR_BRIDGE_TOKEN"],NEXT_PUBLIC_AUTH_ENABLED="true",DEEPTUTOR_AUTH_ENABLED="true")
 return [str(node),"server.js"],web,front

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--root",type=Path,required=True);parser.add_argument("--service",choices=["host","worker","web"],required=True)
 mode=parser.add_mutually_exclusive_group(required=True);mode.add_argument("--check",action="store_true");mode.add_argument("--run",action="store_true");args=parser.parse_args()
 secrets=args.root.resolve()/"private/runtime.env"
 if not secrets.is_file():raise ValueError("private_runtime_config_missing")
 if os.name!="nt" and secrets.stat().st_mode&0o077:raise ValueError("private_runtime_config_permissions")
 command,cwd,env=plan(args.root,args.service,dict(dotenv_values(secrets)))
 if args.check:print(json.dumps({"service":args.service,"checked":True,"cwd":str(cwd)}));return
 os.chdir(cwd);os.execvpe(command[0],command,env)
if __name__=="__main__":main()
