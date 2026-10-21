"""固定/核验候选交付身份；不调用模型，不发布教材，不搬移索引内部路径。"""
import argparse,json,sys,platform,importlib.metadata
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--lock',type=Path,required=True)
 p.add_argument('--write-lock',action='store_true');a=p.parse_args();candidate=a.candidate.resolve(strict=True)
 from knowledge.lightrag.retrieval import LightRagBackend
 from knowledge.lightrag.course_input import COURSE,digest
 from knowledge.lightrag.engine import _require_exact_version
 _require_exact_version();LightRagBackend(candidate,authorized_course_ids={COURSE},allow_candidate=True).validate(COURSE)
 meta=json.loads((candidate/'index/meta.json').read_text(encoding='utf-8'))
 names=['input_manifest.json','q2_input_manifest.json','source_map.json','policy.json','index_files.json','index/meta.json']
 index=json.loads((candidate/'index_files.json').read_text(encoding='utf-8'))
 files={name:digest(candidate/name) for name in names}
 for relative,value in index.items():
  actual=digest(candidate/'index'/relative);assert actual==value
  files['index/'+relative]=actual
 if a.write_lock:
  assert not a.lock.exists(),'拒绝覆盖已有交付锁；身份变化须另建交付'
  import onnxruntime
  modules=['lightrag-hku','openai','fastembed','onnxruntime-gpu','onnxruntime','numpy','pydantic','networkx','psutil','langchain-text-splitters','fastapi','uvicorn','sqlalchemy']
  versions={}
  for name in modules:
   try:versions[name]=importlib.metadata.version(name)
   except importlib.metadata.PackageNotFoundError:versions[name]=None
  lock={'schema':1,'course_id':COURSE,'candidate':str(candidate),'input_signature':candidate.name,
    'files':files,'embedding_model':meta['embedding_model'],'embedding_dimension':meta['embedding_dim'],
    'embedding_signature':meta['embedding_signature'],'policy':meta['indexing_policy'],
    'python':platform.python_version(),'observed_distributions':versions,'loaded_onnxruntime_module':onnxruntime.__version__,
    'state':'candidate only; staging; ready=false','relocation':'fixed local paths; preserve source_root and SDK sidecar paths',
    'dependency_note':'observed local environment; base packages are read-only borrowed, not a complete deployment lock'}
  a.lock.parent.mkdir(parents=True,exist_ok=True);a.lock.write_text(json.dumps(lock,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 expected=json.loads(a.lock.read_text(encoding='utf-8'));assert expected['files']==files,'交付文件签名已变化'
 assert expected['embedding_signature']==meta['embedding_signature']
 assert Path(expected['candidate']).resolve()==candidate,'固定本机交付路径变化，须另行验证内部路径迁移'
 print(json.dumps({'verified':True,'lock_sha256':digest(a.lock),'candidate':str(candidate),'input_signature':candidate.name,'formal_switch':False},ensure_ascii=False))
if __name__=='__main__':main()
