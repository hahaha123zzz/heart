"""全11章真实建图入口；数据与密钥只读，不切换正式索引。"""
import argparse,asyncio,os,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--env-file",type=Path,required=True)
    parser.add_argument("--output",type=Path,default=ROOT/".runtime/lightrag")
    parser.add_argument("--retries",type=int,default=2)
    parser.add_argument("--resume-candidate",type=Path)
    args=parser.parse_args()
    from dotenv import load_dotenv
    if not args.env_file.is_file(): raise FileNotFoundError("缺少已有模型配置文件")
    load_dotenv(args.env_file,override=False)
    os.environ.setdefault("OMP_NUM_THREADS","2");os.environ.setdefault("MKL_NUM_THREADS","2")
    os.environ.setdefault("TOKENIZERS_PARALLELISM","false")
    from knowledge.lightrag.pipeline import build_book
    candidate,state=asyncio.run(build_book(args.source,args.output,retries=args.retries,resume_candidate=args.resume_candidate))
    print(json.dumps({"candidate":str(candidate),"state":state["state"],"graph":state.get("graph")},ensure_ascii=False))
    return 0 if state["state"]=="candidate_complete" else 1
if __name__=="__main__": raise SystemExit(main())
