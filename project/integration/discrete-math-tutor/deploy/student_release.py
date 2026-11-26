"""学生新版源码发行快照和部署选择；不接触学生存储，不自动重启服务。"""
from __future__ import annotations
import argparse,hashlib,json,os,re,shutil
from pathlib import Path

HROOT=Path("project/integration/discrete-math-tutor")
VROOT=Path("project/vendor/DeepTutor")
EXCLUDE={"node_modules",".next",".git",".runtime","__pycache__",".pytest_cache",".venv",".venv-runtime",".venv-deeptutor","artifacts",".cache"}
H_FOLDERS={"agents","database","deploy","frontend","integrations","llm","memory","models","reader","scripts","knowledge","third_party","visualization","visualization-client"}
V_FOLDERS={"deeptutor","deeptutor_cli","config","configs","web","LOCAL_PATCHES","assets","deeptutor_web","packaging","requirements","scripts"}
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def label(value):
 if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}",value):raise ValueError("invalid_release_id")
 return value

def safe_files(root,folders):
 for directory,dirs,names in os.walk(root,followlinks=False):
  base=Path(directory)
  if base==root/"knowledge":dirs[:]=[d for d in dirs if d not in {"courses","pdf","textbook_text","figure_assets","extracted_multimodal","imported_wordopenxml"}]
  dirs[:]=sorted(d for d in dirs if d not in EXCLUDE and not d.startswith((".venv",".next")) and (base!=root or d in folders) and (base/d).resolve()==(base/d).absolute())
  for name in sorted(names):
   p=base/name
   if p.is_symlink() or not p.is_file() or p.resolve()!=p.absolute():continue
   if p.name.startswith(".env") or p.suffix in {".log",".pyc",".pem",".key"} or "accounts.txt" in p.name:continue
   yield p

def bundle(repo,output,release_id):
 repo=repo.resolve(strict=True);output=output.absolute();release_id=label(release_id)
 if output.exists():raise ValueError("output_exists")
 if output.is_relative_to(repo/HROOT) or output.is_relative_to(repo/VROOT):raise ValueError("output_inside_source")
 output.mkdir(parents=True)
 files={}
 for relative,folders in ((HROOT,H_FOLDERS),(VROOT,V_FOLDERS)):
  for source in safe_files(repo/relative,folders):
   rel=source.relative_to(repo);target=output/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target);files[rel.as_posix()]=digest(target)
 for name in ("LICENSE","NOTICE"):
  source=repo/name
  if source.is_file():shutil.copyfile(source,output/name);files[name]=digest(output/name)
 manifest={"format":1,"release_id":release_id,"kind":"source_snapshot_requires_target_build","files":files,"mutable_stores_included":False,"needs_external":["DEEPTUTOR_HOME","PostgreSQL business/memory/LightRAG","course assets","HEART_MODEL_ENCRYPTION_KEY","auth secret","target Python environment","target Node build"]}
 (output/"release.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 verify(output);return manifest

def _inventory(root):
 actual=set()
 for directory,dirs,names in os.walk(root,followlinks=False):
  dirs[:]=[d for d in dirs if d not in {"node_modules",".next",".cache","__pycache__"}]
  for name in names:
   file=Path(directory)/name
   if file!=root/"release.json":actual.add(file.relative_to(root).as_posix())
 return actual

def _manifest(root):
 manifest=json.loads((root/"release.json").read_text("utf-8"));label(manifest["release_id"])
 if manifest.get("format")!=1 or manifest.get("mutable_stores_included") is not False or not isinstance(manifest.get("files"),dict):raise ValueError("invalid_manifest")
 return manifest

def _listed_files(root,manifest):
 for rel in manifest["files"]:
  if not (root/rel).is_file():raise ValueError("release_file_missing:"+rel)
 return set(manifest["files"])

def inspect(root):
 """只核对清单、路径与文件是否存在；逐文件哈希留给显式 verify。"""
 root=root.resolve(strict=True);manifest=_manifest(root);listed=_listed_files(root,manifest)
 if _inventory(root)!=listed:raise ValueError("release_file_inventory_changed")
 for rel in listed:
  p=root/rel
  if not p.resolve().is_relative_to(root) or p.resolve()!=p.absolute():raise ValueError("release_file_missing:"+rel)
 return manifest

def verify(root):
 root=root.resolve(strict=True);manifest=_manifest(root);listed=_listed_files(root,manifest)
 if _inventory(root)!=listed:raise ValueError("release_file_inventory_changed")
 for rel,expected in manifest["files"].items():
  p=root/rel
  if not p.resolve().is_relative_to(root) or p.resolve()!=p.absolute() or digest(p)!=expected:raise ValueError("release_hash_mismatch:"+rel)
 return manifest

def select(root,release,expected_current):
 """只修改代码选择文件；由受控服务启动器重启，不恢复数据备份。"""
 root=root.resolve(strict=True);release=release.resolve(strict=True)
 if not release.is_relative_to(root/"releases"):raise ValueError("release_outside_deployment")
 manifest=inspect(release);pointer=root/"active-release.json"
 from filelock import FileLock
 with FileLock(str(root/".release-select.lock"),timeout=0):
  current=json.loads(pointer.read_text("utf-8")) if pointer.exists() else None
  if (current or {}).get("release_id")!=expected_current:raise ValueError("current_release_changed")
  value={"release_id":manifest["release_id"],"release_path":str(release),"previous_release_id":(current or {}).get("release_id"),"restart_required":True,"student_data_changed":False}
  tmp=root/"active-release.json.tmp"
  with tmp.open("x",encoding="utf-8") as file:json.dump(value,file,ensure_ascii=False,indent=2)
  os.replace(tmp,pointer);return value

def main():
 parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest="command",required=True)
 pack=commands.add_parser("bundle");pack.add_argument("--repo",type=Path,required=True);pack.add_argument("--output",type=Path,required=True);pack.add_argument("--release-id",required=True)
 check=commands.add_parser("verify");check.add_argument("--release",type=Path,required=True)
 choose=commands.add_parser("select");choose.add_argument("--root",type=Path,required=True);choose.add_argument("--release",type=Path,required=True);choose.add_argument("--expected-current")
 args=parser.parse_args()
 if args.command=="bundle":result=bundle(args.repo,args.output,args.release_id)
 elif args.command=="verify":result=verify(args.release)
 else:result=select(args.root,args.release,args.expected_current)
 print(json.dumps({k:result[k] for k in ("release_id","kind","restart_required","student_data_changed") if k in result}))
if __name__=="__main__":main()
