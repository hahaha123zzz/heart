"""受控管理本机学生测试进程，仅停止自己登记且身份匹配的进程。"""
from __future__ import annotations
import argparse,json,os,socket,subprocess,time
from pathlib import Path
import psutil
from dotenv import dotenv_values
from filelock import FileLock
try:
 from .run_student_release import plan
except ImportError:
 from run_student_release import plan

def matching(record):
 try:
  p=psutil.Process(record["pid"])
  return p if abs(p.create_time()-record["created_at"])<.01 and p.cmdline()==record["command"] else None
 except (psutil.NoSuchProcess,psutil.AccessDenied,KeyError):return None

def stop(records):
 for row in records.values():
  process=matching(row)
  if process is None:continue
  children=process.children(recursive=True)
  for child in reversed(children):
   try:child.terminate()
   except psutil.NoSuchProcess:pass
  try:process.terminate()
  except psutil.NoSuchProcess:pass
  _,alive=psutil.wait_procs([*children,process],timeout=10)
  for child in alive:
   try:child.kill()
   except psutil.NoSuchProcess:pass

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("action",choices=["start","stop","restart","status"]);parser.add_argument("--root",type=Path,required=True);args=parser.parse_args();root=args.root.resolve(strict=True);private=root/"private";file=private/"services.json"
 with FileLock(str(private/"services.lock"),timeout=0):
  records=json.loads(file.read_text("utf-8")) if file.exists() else {}
  if args.action=="status":print(json.dumps({key:{"pid":row["pid"],"running":matching(row) is not None} for key,row in records.items()}));return
  if args.action in {"stop","restart"}:stop(records);records={};file.write_text("{}",encoding="utf-8")
  if args.action=="stop":print('{"stopped":true}');return
  values={k:v for k,v in dotenv_values(private/"runtime.env").items() if isinstance(v,str)}
  ports={"host":int(values.get("HEART_HOST_PORT","8000")),"worker":int(values.get("HEART_WORKER_PORT","18001")),"web":int(values.get("HEART_WEB_PORT","3782"))}
  logs=private/"logs";logs.mkdir(exist_ok=True)
  for service in ("host","worker","web"):
   if service in records and matching(records[service]) is not None:continue
   with socket.socket() as probe:probe.bind(("127.0.0.1",ports[service]))
   command,cwd,env=plan(root,service,values)
   with (logs/(service+".log")).open("ab") as log:
    process=subprocess.Popen(command,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0,start_new_session=os.name!="nt")
   owner=psutil.Process(process.pid);records[service]={"pid":process.pid,"created_at":owner.create_time(),"command":owner.cmdline()};file.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding="utf-8")
  import httpx
  with httpx.Client(trust_env=False,timeout=3) as client:
   for service,path in (("host","/health"),("worker","/health/ready"),("web","/login")):
    for attempt in range(180):
     if matching(records[service]) is None:raise RuntimeError("service_stopped:"+service+";inspect_private_logs")
     try:
      response=client.get("http://127.0.0.1:"+str(ports[service])+path)
      if response.status_code==200:break
     except httpx.HTTPError:pass
     time.sleep(1)
    else:raise RuntimeError("readiness_timeout:"+service)
  print(json.dumps({"url":"http://127.0.0.1:"+str(ports["web"]),"services":{name:row["pid"] for name,row in records.items()},"ready":True}))
if __name__=="__main__":main()
