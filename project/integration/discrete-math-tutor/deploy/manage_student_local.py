"""受控管理本机学生测试进程，仅停止自己登记且身份匹配的进程。"""
from __future__ import annotations
import argparse,json,os,socket,subprocess,threading,time
from datetime import datetime
from pathlib import Path
import psutil
from dotenv import dotenv_values
from filelock import FileLock
try:
 from .run_student_release import plan
except ImportError:
 from run_student_release import plan

PROBES=(("host","/health"),("worker","/health/ready"),("web","/login"))

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

def recorder(directory, sid, name):
 # 控制脚本在发行目录外运行，不能导入应用包；沿用同一 JSONL 口径。
 lock=threading.Lock();path=directory/(f"{name}-{os.getpid()}.jsonl")
 def record(stage,*,parent=None,seconds=0.0,status="ok",**fields):
  row={"startup_id":sid,"service":name,"pid":os.getpid(),"stage":stage,"parent":parent,
       "seconds":round(float(seconds),4),"status":status,"fields":fields,
       "at":datetime.now().astimezone().isoformat(timespec="milliseconds")}
  with lock:
   directory.mkdir(parents=True,exist_ok=True)
   with path.open("a",encoding="utf-8") as stream:
    stream.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+"\n")
  return row
 return record

def probe(record,ports,origin):
 # 独立并行探测三个端口，与控制脚本顺序阻塞的就绪检查分开计时。
 import httpx
 stop_event=threading.Event()
 def watch(service,path):
  client=httpx.Client(trust_env=False,timeout=3);attempts=0
  try:
   while True:
    attempts+=1
    try:
     if client.get("http://127.0.0.1:"+str(ports[service])+path).status_code==200:
      record("probe.first_ok",parent="probe",seconds=time.perf_counter()-origin,
             target=service,attempts=attempts);return
    except httpx.HTTPError:pass
    if stop_event.is_set():
     record("probe.stopped",parent="probe",status="failed",seconds=time.perf_counter()-origin,
            target=service,attempts=attempts);return
    stop_event.wait(.2)
  finally:client.close()
 for service,path in PROBES:
  threading.Thread(target=watch,args=(service,path),daemon=True).start()
 return stop_event

def launch(pending, spawn, ready):
 # worker 预热接近或超过宿主的 60 秒等待预算，必须先独立就绪再启动宿主与 Web。
 for service in pending:
  if service=="worker":spawn(service);ready(service)
 for service in pending:
  if service!="worker":spawn(service)
 for service in pending:
  if service!="worker":ready(service)

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("action",choices=["start","stop","restart","status"]);parser.add_argument("--root",type=Path,required=True)
 parser.add_argument("--label",default=None);parser.add_argument("--cache-state",choices=["process-cold","os-warm","unknown"],default="process-cold")
 args=parser.parse_args();root=args.root.resolve(strict=True);private=root/"private";file=private/"services.json"
 with FileLock(str(private/"services.lock"),timeout=0):
  records=json.loads(file.read_text("utf-8")) if file.exists() else {}
  if args.action=="status":print(json.dumps({key:{"pid":row["pid"],"running":matching(row) is not None} for key,row in records.items()}));return
  if args.action in {"stop","restart"}:stop(records);records={};file.write_text("{}",encoding="utf-8")
  if args.action=="stop":print('{"stopped":true}');return
  values={k:v for k,v in dotenv_values(private/"runtime.env").items() if isinstance(v,str)}
  ports={"host":int(values.get("HEART_HOST_PORT","8000")),"worker":int(values.get("HEART_WORKER_PORT","18001")),"web":int(values.get("HEART_WEB_PORT","3782"))}
  logs=private/"logs";logs.mkdir(exist_ok=True)
  sid=os.getenv("STARTUP_ID") or time.strftime("%Y%m%dT%H%M%S")+"-"+str(os.getpid())
  directory=private/"startup-traces"/sid
  record=recorder(directory,sid,"control");probe_record=recorder(directory,sid,"probe")
  origin=time.perf_counter()
  record("control.begin",parent="control",seconds=0,label=args.label,cache_state=args.cache_state,
         host_port=ports["host"],worker_port=ports["worker"],web_port=ports["web"])
  os.environ["STARTUP_ID"]=sid;os.environ["STARTUP_TRACE_DIR"]=str(directory)
  keeper=probe(probe_record,ports,origin)
  status="ok";target=None
  try:
   pending=[service for service in ("worker","host","web")
            if not (service in records and matching(records[service]) is not None)]
   def spawn(service):
    nonlocal target
    target=service
    with socket.socket() as sock:sock.bind(("127.0.0.1",ports[service]))
    timing={};began=time.perf_counter();planned=False
    try:
     command,cwd,env=plan(root,service,values,timing);planned=True
    finally:
     record("control.release_verify",parent="control.service",
            seconds=timing.get("release_seconds",time.perf_counter()-began),
            target=service,release_id=timing.get("release_id"),files=timing.get("file_count"),
            status="ok" if planned else "failed")
    env["STARTUP_SERVICE"]=service
    spawn_at=time.perf_counter()
    with (logs/(service+".log")).open("ab") as log:
     process=subprocess.Popen(command,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0,start_new_session=os.name!="nt")
    owner=psutil.Process(process.pid);records[service]={"pid":process.pid,"created_at":owner.create_time(),"command":owner.cmdline()};file.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding="utf-8")
    record("control.process_start",parent="control.service",seconds=time.perf_counter()-spawn_at,
           target=service,pid=process.pid)
   import httpx
   with httpx.Client(trust_env=False,timeout=3) as client:
    def ready(service):
     nonlocal target
     target=service
     path=dict(PROBES)[service];began=time.perf_counter();attempts=0
     for attempt in range(180):
      attempts=attempt+1
      if matching(records[service]) is None:raise RuntimeError("service_stopped:"+service+";inspect_private_logs")
      try:
       response=client.get("http://127.0.0.1:"+str(ports[service])+path)
       if response.status_code==200:break
      except httpx.HTTPError:pass
      time.sleep(1)
     else:raise RuntimeError("readiness_timeout:"+service)
     record("control.ready",parent="control.service",seconds=time.perf_counter()-began,
            elapsed_since_origin=time.perf_counter()-origin,target=service,attempts=attempts)
    launch(pending,spawn,ready)
  except BaseException as exc:
   status="cancelled" if type(exc).__name__=="CancelledError" else "failed"
   record("control.failed",parent="control",seconds=time.perf_counter()-origin,
          status=status,target=target,error=type(exc).__name__)
   raise
  finally:
   keeper.set()
   record("control.done",parent="control",seconds=time.perf_counter()-origin,status=status)
  print(json.dumps({"url":"http://127.0.0.1:"+str(ports["web"]),"services":{name:row["pid"] for name,row in records.items()},"ready":True,"startup_id":sid,"trace":str(directory)}))
if __name__=="__main__":main()
