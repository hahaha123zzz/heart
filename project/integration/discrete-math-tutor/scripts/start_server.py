"""启动前预热小模型，避免首个提问承担 GPU 初始化开销。"""
import os
import argparse
import time
import faulthandler
import uvicorn
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--rerank-device", choices=("cpu","cuda"))
    args=parser.parse_args()
    started=time.perf_counter()
    faulthandler.dump_traceback_later(60, repeat=True)
    def stage(label):
        print(f"启动阶段：{label}（累计 {time.perf_counter()-started:.1f}s）", flush=True)
    stage("加载应用")
    from main import app
    from knowledge.hybrid_retrieval import _embedder, _reranker, _vectors, INDEX
    from knowledge.inference_runtime import runtime_status
    from knowledge.course_config import PSYCHOLOGY
    warm_query='自变量和因变量' if PSYCHOLOGY else '逻辑合取'
    warm_text='自变量是研究者操纵的变量，因变量是观察或测量的变量。' if PSYCHOLOGY else '两个命题都为真时，合取为真。'
    if args.rerank_device:
        os.environ["RAG_RERANK_DEVICE"]=args.rerank_device
    stage("读取检索索引")
    name, _ = _vectors(str(INDEX), INDEX.stat().st_mtime_ns)
    if name:
        stage("预热 embedding")
        list(_embedder(name).embed([warm_query]))
        stage("embedding 已就绪")
    rerank_name = os.environ.get("RAG_RERANK_MODEL", "").strip()
    if rerank_name:
        stage("预热 reranker")
        backend, model = _reranker(rerank_name)
        if backend == "fastembed":
            list(model.rerank(warm_query, [warm_text], batch_size=1))
        else:
            model.compute_score([[warm_query, warm_text]])
    faulthandler.cancel_dump_traceback_later()
    stage("模型预热完成")
    print("RAG runtime:", runtime_status(), flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port)
