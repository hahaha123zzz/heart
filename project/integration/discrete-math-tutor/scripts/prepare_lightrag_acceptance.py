"""固定已提交宿主与只读旧索引副本；不复制主工作树未提交文件。"""
import argparse,hashlib,io,json,subprocess,sys,tarfile,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parents[2]
sys.path.insert(0,str(ROOT))

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--host-revision',required=True)
 p.add_argument('--baseline-index',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 candidate=a.candidate.resolve(strict=True);out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
 from knowledge.lightrag.retrieval import LightRagBackend
 from knowledge.lightrag.course_input import COURSE,digest
 LightRagBackend(candidate,authorized_course_ids={COURSE},allow_candidate=True).validate(COURSE)
 rev=subprocess.check_output(['git','rev-parse',a.host_revision+'^{commit}'],cwd=REPO,text=True).strip()
 prefix='project/integration/discrete-math-tutor/'
 names=subprocess.check_output(['git','ls-tree','-r','--name-only',rev,'--',prefix],cwd=REPO,text=True,encoding='utf-8').splitlines()
 names=[n for n in names if n.endswith('.py') or n.startswith(prefix+'agents/') and n.endswith('.json')]
 host=out/'host';marker=out/'host_revision.txt'
 if marker.exists():assert marker.read_text().strip()==rev,'宿主提交发生变化，请用新的隔离目录'
 else:
  assert not host.exists(),'拒绝覆盖未登记宿主'
  archive=subprocess.check_output(['git','archive',rev,'--',*names],cwd=REPO)
  host.mkdir()
  with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
   for item in tar:
    if item.isfile():
     dst=host/Path(item.name).relative_to(prefix)
     assert dst.resolve().is_relative_to(host.resolve())
     dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(tar.extractfile(item).read())
  marker.write_text(rev+'\n')
 expected=json.loads((candidate/'q2_input_manifest.json').read_text(encoding='utf-8'))['existing_index']['sha256']
 source=a.baseline_index.resolve(strict=True)
 assert not Path(str(source)+'-wal').exists(),'旧索引正在写入'
 assert digest(source)==expected,'旧索引已不同于Q2固定交付'
 target=out/'baseline.sqlite3'
 if not target.exists():shutil.copyfile(source,target)
 assert digest(target)==expected==digest(source)
 report={'host_revision':rev,'host':str(host),'candidate':str(candidate),'baseline_index':str(target),
         'baseline_sha256':expected,'database':str(out/'students.sqlite3'),'input_signature':candidate.name,
         'source':'committed host only; baseline index matches Q2 delivery; candidate input unchanged'}
 (out/'isolation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
