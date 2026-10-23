"""准备固定代码/教材导出及待批准启动器；不复制学生库、不启动或停止服务。"""
import argparse,hashlib,json,shutil,subprocess,zipfile
from pathlib import Path

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--production-repo',type=Path,required=True);parser.add_argument('--previous-setup',type=Path,required=True);parser.add_argument('--previous-launcher',type=Path,required=True);args=parser.parse_args()
 repo=Path(__file__).resolve().parents[4];out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
 revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
 archive=out/'source.zip';subprocess.run(['git','archive','--format=zip','--output',str(archive),revision],cwd=repo,check=True)
 code=out/'code';code.mkdir()
 with zipfile.ZipFile(archive) as bundle:
  assert all((code/name).resolve().is_relative_to(code) for name in bundle.namelist())
  bundle.extractall(code)
 app=code/'project/integration/discrete-math-tutor';assert (app/'knowledge/visual_locations.py').is_file()
 previous=json.loads(args.previous_setup.read_text(encoding='utf-8'));source=Path(previous['input']);target=app/'knowledge/courses/experimental-psychology-3';target.mkdir(parents=True,exist_ok=True)
 resources=[]
 for file in source.rglob('*'):
  if not file.is_file() or '__pycache__' in file.parts:continue
  dest=target/file.relative_to(source);dest.parent.mkdir(parents=True,exist_ok=True);before=sha(file);shutil.copy2(file,dest);assert sha(dest)==before==sha(file)
  resources.append({'file':str(dest),'sha256':before})
 manifest=[{'file':str(file),'sha256':sha(file)} for file in code.rglob('*') if file.is_file()]
 (out/'files.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
 setup=previous|{'revision':revision,'release':str(app),'input':str(target)}
 (out/f'setup-{revision}.json').write_text(json.dumps(setup,ensure_ascii=False,indent=2),encoding='utf-8')
 production=args.production_repo.resolve();launcher=args.previous_launcher.read_text(encoding='utf-8');old=previous['revision']
 launcher=launcher.replace(old,revision).replace('repo=home.parents[1]',f'repo=Path({str(production)!r})')
 launcher=launcher.replace("python=home.parent/'response-release-20261022/.venv/Scripts/python.exe'",f"python=Path({str(production/'.runtime/response-release-20261022/.venv/Scripts/python.exe')!r})")
 launcher=launcher.replace("str(home/'model-cache/fastembed')",f"{str(args.previous_launcher.parent/'model-cache/fastembed')!r}")
 marker="cfg=dotenv_values(repo/'ds.env');"
 preflight="import hashlib\nfor item in json.loads((home/'files.json').read_text(encoding='utf-8')):\n    assert hashlib.sha256(Path(item['file']).read_bytes()).hexdigest()==item['sha256'], '固定导出文件已变化'\n"
 assert marker in launcher;launcher=launcher.replace(marker,preflight+marker)
 launcher_path=out/'start-approved.py';launcher_path.write_text(launcher,encoding='utf-8');compile(launcher,str(launcher_path),'exec')
 result=dict(revision=revision,release=str(app),archive_sha256=sha(archive),code_and_resource_files=len(manifest),course_resource_files=len(resources),candidate=previous['candidate'],launcher=str(launcher_path),launcher_origin_sha256=sha(args.previous_launcher),started=False,student_databases_copied=False,requires_fresh_database_backup_before_enable=True)
 (out/'release.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
