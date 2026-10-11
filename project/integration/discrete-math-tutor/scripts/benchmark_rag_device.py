"""固定题集与模型的设备对照，记录热启动耗时和实际会话。"""
import argparse
import json
import os
import time
from pathlib import Path
import onnxruntime as ort
from knowledge.hybrid_retrieval import _reranker, retrieve_hybrid
from knowledge.inference_runtime import session_providers
from knowledge.textbook import load_textbook
from scripts.eval_rag_holdout import evaluate

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--device", choices=["cpu", "cuda"], required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    os.environ["RAG_RERANK_MODEL"] = "BAAI/bge-reranker-base"
    os.environ["RAG_RERANK_DEVICE"] = a.device
    os.environ["RAG_EMBED_DEVICE"] = "cpu"
    os.environ["RAG_RERANK_MIN_PROBABILITY"] = "0.15"
    t = time.perf_counter()
    backend, model = _reranker("BAAI/bge-reranker-base")
    print("session", session_providers(model), flush=True)
    scores = list(model.rerank("合取什么时候为真？", ["两个命题都为真时合取为真。", "图包含顶点和边。"], batch_size=2))
    cold_seconds = time.perf_counter()-t
    print("probe", scores, "cold_seconds", cold_seconds, flush=True)
    retrieve_hybrid("命题否定的真值是什么？", load_textbook(), limit=3)
    cases = Path("tests/data/rag_blind_reranker_2026_10_10.json")
    report = evaluate(cases, with_trace=True)
    report["device"] = a.device
    report["cold_probe_seconds"] = cold_seconds
    report["onnxruntime"] = ort.__version__
    report["providers"] = session_providers(model)
    latencies = sorted(r["latency_ms"] for r in report["methods"]["hybrid"]["rows"])
    report["p95_latency_ms"] = latencies[min(len(latencies)-1, int(len(latencies)*0.95))]
    a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("done", report["methods"]["hybrid"]["hit_at_2"], report["methods"]["hybrid"]["median_latency_ms"], flush=True)
