"""在独立进程比较默认缓存与固定缓存；不改动系统缓存。"""
import argparse, json, os, subprocess, sys, time
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--child',default='');p.add_argument('--cache-dir',default='');args=p.parse_args()
if not args.child:
    cache=BASE/'artifacts/cuda-cache-experiment-20261011'
    cache.mkdir(parents=True,exist_ok=True)
    for label, directory in [('default',''),('explicit-first',str(cache)),('explicit-restart',str(cache))]:
        print('开始',label,flush=True)
        subprocess.run([sys.executable,'-u','-X','utf8','-m','scripts.diagnose_cuda_startup','--child',label,'--cache-dir',directory],cwd=BASE,check=True,timeout=600)
    raise SystemExit()
if args.cache_dir:
    os.environ['CUDA_CACHE_PATH']=args.cache_dir
started=time.perf_counter()
import onnxruntime as ort
from fastembed.rerank.cross_encoder import TextCrossEncoder
from knowledge.inference_runtime import verify_device
# 对照组直接预加载 DLL，避免应用新增默认缓存覆盖驱动默认环境。
ort.preload_dlls(directory='');dll=time.perf_counter()
m=TextCrossEncoder('BAAI/bge-reranker-base',lazy_load=True,cuda=True,threads=4)
inner=m.model
inner._load_onnx_model(inner._model_dir,inner.model_description.model_file,threads=4,cuda=False)
model=time.perf_counter()
options=ort.SessionOptions();options.enable_profiling=True
options.profile_file_prefix=str(BASE/('artifacts/cuda-startup-'+args.child))
options.intra_op_num_threads=4;options.inter_op_num_threads=4
inner.model=ort.InferenceSession(str(inner._model_dir/inner.model_description.model_file),sess_options=options,providers=['CUDAExecutionProvider'])
verify_device(m,'cuda');session=time.perf_counter()
scores=list(m.rerank('合取什么时候为真？',['两个命题都为真时合取为真。'],batch_size=1));first=time.perf_counter()
scores2=list(m.rerank('合取什么时候为真？',['两个命题都为真时合取为真。'],batch_size=1));second=time.perf_counter()
profile=Path(inner.model.end_profiling());events=json.loads(profile.read_text(encoding='utf8'))
kernels=[e for e in events if e.get('cat')=='Node' and e.get('args',{}).get('provider')=='CUDAExecutionProvider']
cache_value=os.environ.get('CUDA_CACHE_PATH') or (str(Path(os.environ['APPDATA'])/'NVIDIA/ComputeCache') if os.environ.get('APPDATA') else None)
cache=Path(cache_value) if cache_value else None
files=list(cache.rglob('*')) if cache and cache.exists() else []
result={'label':args.child,'seconds':{'imports_dll':dll-started,'model_cpu':model-dll,'cuda_session':session-model,'first_inference':first-session,'second_inference':second-first,'total':second-started},'providers':inner.model.get_providers(),'scores':scores,'scores_repeat':scores2,'cache_path':str(cache) if cache else None,'cache_files':sum(f.is_file() for f in files),'cache_bytes':sum(f.stat().st_size for f in files if f.is_file()),'cuda_events':len(kernels),'slowest_cuda_nodes':[{'name':e['name'],'seconds':e.get('dur',0)/1e6} for e in sorted(kernels,key=lambda e:e.get('dur',0),reverse=True)[:5]],'environment':{n:os.environ.get(n) for n in ['APPDATA','CUDA_CACHE_PATH','CUDA_CACHE_DISABLE','CUDA_CACHE_MAXSIZE','CUDA_FORCE_PTX_JIT','CUDA_MODULE_LOADING']},'profile':str(profile)}
(BASE/('artifacts/cuda-startup-'+args.child+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(result,ensure_ascii=False),flush=True)
