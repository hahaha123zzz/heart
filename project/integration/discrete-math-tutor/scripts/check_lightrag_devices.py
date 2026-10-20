"""同权重CPU/CUDA功能检查；使用少量输入，不作性能基准或压力测试。"""
import argparse,asyncio,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def main():
    parser=argparse.ArgumentParser();parser.add_argument("candidate",type=Path)
    args=parser.parse_args();candidate=args.candidate.resolve(strict=True)
    import numpy as np,onnxruntime as ort
    from knowledge.lightrag.pipeline import embedding_config
    from knowledge.lightrag.config import build_embedding_func
    from knowledge.hybrid_retrieval import _embedder_on_device,_reranker_on_device
    from knowledge.inference_runtime import session_providers
    from knowledge.lightrag.file_io import atomic_write_json
    policy=json.loads((candidate/"policy.json").read_text(encoding="utf-8"))
    texts=["自变量是研究者主动操纵的实验条件。","被试内设计和被试间设计的比较。","第七章差别感觉阈限与PSE。"]
    vectors={};providers={}
    async def run():
        for device in ("cpu","cuda"):
            config=await embedding_config(device=device)
            assert config.signature()==policy["embedding_signature"],"GPU/CPU权重与候选模型身份不同"
            vectors[device]=await build_embedding_func(embedding_config=config).func(texts)
            providers[device]=session_providers(_embedder_on_device(config.model,device))
    asyncio.run(run())
    cos=np.sum(vectors["cpu"]*vectors["cuda"],axis=1)/(np.linalg.norm(vectors["cpu"],axis=1)*np.linalg.norm(vectors["cuda"],axis=1))
    assert np.isfinite(cos).all() and float(cos.min())>.9999,"CPU/GPU数值兼容检查失败"
    backend,reranker=_reranker_on_device("BAAI/bge-reranker-base","cuda")
    assert backend=="fastembed"
    scores=list(reranker.rerank("什么是自变量",[texts[0],"火星玄武岩的晶体结构"],batch_size=2))
    assert len(scores)==2 and np.isfinite(scores).all() and scores[0]>scores[1]
    report={"passed":True,"scope":"3 embedding inputs + 2 reranking inputs; functional check only",
            "embedding_signature":policy["embedding_signature"],"onnxruntime_module_version":ort.__version__,
            "providers":providers,"minimum_cosine":float(cos.min()),
            "max_absolute_difference":float(np.max(np.abs(vectors["cpu"]-vectors["cuda"]))),
            "reranker_providers":session_providers(reranker),"reranker_scores":[float(s) for s in scores]}
    atomic_write_json(candidate/"device_validation.json",report);print(json.dumps(report,ensure_ascii=False))
if __name__=="__main__":main()
